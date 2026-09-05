import test from "node:test";
import assert from "node:assert/strict";
await import("../shazam-logic.js");
await import("../shazam.js");
const logic=globalThis.EasyMP3Shazam;
const redirect=globalThis.EasyMP3ShazamRedirect;
const node=(textContent="",extra={})=>({textContent,...extra});
function fixture({title,artist,scripts=[],menuLinks=[]}={}){const links=menuLinks.map(h=>({href:h}));const menu={querySelectorAll:()=>links};return{querySelector(selector){if(selector==="main")return this;if(selector.startsWith("a[data-test-id"))return null;if(selector.includes("trackTitle"))return title?node(title):null;if(selector.includes("track_userevent_artist_link"))return artist?node(artist):null;return null;},querySelectorAll(selector){if(selector.startsWith("script"))return scripts.map(value=>node(JSON.stringify(value)));if(selector.includes("[role='menu']"))return menuLinks.length?[menu]:[];return[];}};}
test("accepts only an allowlisted YouTube menu target, including search links",()=>{const doc=fixture({menuLinks:["https://evil.test/?next=https://youtube.com/watch?v=abcdefghijk","https://www.youtube.com/results?search_query=real"]});assert.equal(logic.directLink(doc),"https://www.youtube.com/results?search_query=real");});
test("finds the verified Shazam YouTube action in its visible portal menu", () => {
  const menu = { getAttribute: name => name === "aria-hidden" ? "false" : null };
  const link = {
    href: "https://www.youtube.com/results?search_query=Biological%20By%20X-Side",
    closest: selector => selector === "[role='menu']" ? menu : null,
  };
  const doc = { querySelector: () => link, querySelectorAll: () => [] };
  assert.equal(logic.directLink(doc), link.href);
});
test("does not use unrelated YouTube links outside the song menu",()=>{assert.equal(logic.directLink(fixture()),null);});
test("prefers real track title and artist selectors over JSON",()=>{assert.deepEqual(logic.songData(fixture({title:"Visible Song",artist:"Full Artist",scripts:[{"@type":"MusicRecording",name:"Wrong",byArtist:"Wrong"}]}),"/song/123/name"),{title:"Visible Song",artist:"Full Artist"});});
test("matches structured data to the current song and supports string byArtist",()=>{const scripts=[{"@graph":[{"@type":"MusicRecording",url:"https://www.shazam.com/song/999/other",name:"Other",byArtist:"Other Artist"},{"@type":"MusicRecording",url:"https://www.shazam.com/song/123/right",name:"Right",byArtist:"Right Artist"}]}];assert.deepEqual(logic.songData(fixture({scripts}),"/en-gb/song/123/right"),{title:"Right",artist:"Right Artist"});});
test("finds the More options button in the current Shazam track header",()=>{
  const button={ariaLabel:"More options"};
  const track={querySelector:selector=>selector.includes("more options")?button:null};
  const title={closest:selector=>selector.includes("NewTrackPageHeader_trackContent")?track:null};
  const doc={querySelector:selector=>selector.includes("trackTitle")?title:null};
  assert.equal(logic.menuButton(doc),button);
});

function harness(overrides={}) {
  let time=0;
  let observer;
  let sequence=0;
  const pending=[];
  class FakeObserver {
    constructor(callback){this.callback=callback;this.disconnected=false;observer=this;}
    observe(){}
    disconnect(){this.disconnected=true;}
    mutate(){this.callback();}
  }
  const page={pathname:"/song/123/song",replaced:[],replace(value){this.replaced.push(value);}};
  const doc={documentElement:{}};
  const state={direct:null,data:{title:null,artist:null},menu:null};
  const fakeLogic={
    directLink:()=>state.direct,
    songData:()=>state.data,
    searchUrl:data=>data.title&&data.artist?`search:${data.title}:${data.artist}`:null,
    menuButton:()=>state.menu,
  };
  const setTimer=(callback,delay)=>{const id=++sequence;pending.push({id,at:time+delay,callback});return id;};
  const clearTimer=id=>{const item=pending.find(value=>value.id===id);if(item)item.cancelled=true;};
  const tick=milliseconds=>{const end=time+milliseconds;for(;;){pending.sort((a,b)=>a.at-b.at);const item=pending.find(value=>!value.cancelled&&value.at<=end);if(!item)break;pending.splice(pending.indexOf(item),1);time=item.at;item.callback();}time=end;};
  const controller=redirect.startRedirect({document:doc,location:page,logic:fakeLogic,MutationObserver:FakeObserver,now:()=>time,setTimeout:setTimer,clearTimeout:clearTimer,...overrides});
  return {controller,doc,fakeLogic,observer:()=>observer,page,state,tick};
}

test("redirects on the mutation that adds the direct link, before the safety poll",()=>{
  const run=harness();
  run.state.direct="https://www.youtube.com/watch?v=abcdefghijk";
  run.observer().mutate();
  assert.deepEqual(run.page.replaced,[run.state.direct]);
});

test("uses metadata fallback after a 100 ms grace period",()=>{
  const run=harness();
  run.state.data={title:"Song",artist:"Artist"};
  run.observer().mutate();
  run.tick(99);
  assert.deepEqual(run.page.replaced,[]);
  run.tick(1);
  assert.deepEqual(run.page.replaced,["search:Song:Artist"]);
});

test("opens the primary menu only once even if its DOM node is replaced",()=>{
  const run=harness();
  let clicks=0;
  run.state.menu={click(){clicks++;}};
  run.observer().mutate();
  run.state.menu={click(){clicks++;}};
  run.observer().mutate();
  assert.equal(clicks,1);
});

test("disabled redirect does not observe or navigate",()=>{
  let constructed=false;
  class Observer {constructor(){constructed=true;}}
  const page={pathname:"/song/123/song",replace(){throw new Error("must not navigate");}};
  redirect.startRedirect({enabled:false,document:{documentElement:{}},location:page,MutationObserver:Observer});
  assert.equal(constructed,false);
});

test("stops without redirect when song metadata never arrives",()=>{
  const run=harness();
  run.tick(10100);
  assert.deepEqual(run.page.replaced,[]);
  assert.equal(run.observer().disconnected,true);
});

test("does not follow a direct link left behind by the previous song route",()=>{
  const run=harness();
  run.page.pathname="/song/456/new-song";
  run.state.direct="https://www.youtube.com/watch?v=oldoldold01";
  run.observer().mutate();
  run.observer().mutate();
  assert.deepEqual(run.page.replaced,[]);
  run.state.direct=null;
  run.observer().mutate();
  run.state.direct="https://www.youtube.com/watch?v=newnewnew01";
  run.observer().mutate();
  assert.deepEqual(run.page.replaced,[run.state.direct]);
});

test("does not build a fallback from metadata left behind by the previous route",()=>{
  const run=harness();
  run.state.data={title:"Old Song",artist:"Old Artist"};
  run.page.pathname="/song/456/new-song";
  run.observer().mutate();
  run.tick(200);
  assert.deepEqual(run.page.replaced,[]);
  run.state.data={title:"New Song",artist:"New Artist"};
  run.observer().mutate();
  run.tick(100);
  assert.deepEqual(run.page.replaced,["search:New Song:New Artist"]);
});
