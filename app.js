/* FH6 Road Finder - Live browser-based pixel scanner */
(function(){
"use strict";

var TOL_NAMES = {0:"Ultra strict",1:"Strict",2:"Normal",5:"Loose",8:"Very loose"};

// DOM
var dropZone=document.getElementById("drop-zone");
var fileInput=document.getElementById("file-input");
var imageInfo=document.getElementById("image-info");
var sourceCanvas=document.getElementById("source-canvas");
var sourceCtx=sourceCanvas.getContext("2d");
var viewerLayout=document.getElementById("viewer-layout");
var tolSlider=document.getElementById("tolerance-slider");
var tolValue=document.getElementById("tolerance-value");
var thickSlider=document.getElementById("thickness-slider");
var thickValue=document.getElementById("thickness-value");
var clusterSlider=document.getElementById("min-cluster");
var clusterValue=document.getElementById("cluster-value");
var targetPicker=document.getElementById("target-picker");
var targetRGB=document.getElementById("target-rgb");
var targetDisp=document.getElementById("target-rgb-display");
var swatches=document.getElementById("highlight-swatches");
var hlPicker=document.getElementById("highlight-picker");
var hlRGB=document.getElementById("highlight-rgb");
var cycleColours=document.getElementById("cycle-colours");
var cycleSpeed=document.getElementById("cycle-speed");
var cycleSpeedValue=document.getElementById("cycle-speed-value");
var modeBtns=document.getElementById("mode-buttons");
var outMode=document.getElementById("output-mode");
var downloadBtn=document.getElementById("download-btn");
var dlMode=document.getElementById("download-mode");
var resetBtn=document.getElementById("reset-btn");
var statsEl=document.getElementById("results-stats");
var viewer=document.getElementById("viewer-container");
var outCanvas=document.getElementById("output-canvas");
var outCtx=outCanvas.getContext("2d");
var zoomInBtn=document.getElementById("zoom-in-btn");
var zoomOutBtn=document.getElementById("zoom-out-btn");
var zoomFitBtn=document.getElementById("zoom-fit-btn");
var zoom100Btn=document.getElementById("zoom-100-btn");
var zoomSpan=document.getElementById("zoom-level");

// State
var srcData=null, rawMask=null, dilatedMask=null;
var imgW=0, imgH=0;
var zoomScale=1, panX=0, panY=0;
var isPanning=false, psx=0, psy=0, ppx=0, ppy=0;
var scanTimer=null;
var cycleTimer=null, cycleFrame=0;
var CYCLE_COLOURS=[[255,0,0],[255,255,0],[0,255,255],[255,0,255],[0,255,0],[255,165,0]];

function fmt(n){return n.toLocaleString();}
function hex2rgb(h){return[parseInt(h.substr(1,2),16),parseInt(h.substr(3,2),16),parseInt(h.substr(5,2),16)];}
function rgb2hex(r,g,b){return"#"+[r,g,b].map(function(c){return c.toString(16).padStart(2,"0");}).join("");}

function getSettings(){
  var tp=targetRGB.value.split(",").map(Number);
  var hp=hlRGB.value.split(",").map(Number);
  if(cycleColours.checked) hp=CYCLE_COLOURS[cycleFrame%CYCLE_COLOURS.length];
  return{
    tR:tp[0],tG:tp[1],tB:tp[2],
    tol:parseInt(tolSlider.value,10),
    hR:hp[0],hG:hp[1],hB:hp[2],
    thickness:parseInt(thickSlider.value,10),
    minCluster:parseInt(clusterSlider.value,10)||1,
    mode:outMode.value
  };
}

// === Settings UI ===
tolSlider.addEventListener("input",function(){
  var v=parseInt(this.value,10), n=TOL_NAMES[v];
  tolValue.textContent=n?v+" ("+n+")":String(v);
  scheduleScan();
});
thickSlider.addEventListener("input",function(){
  var v=parseInt(this.value,10);
  thickValue.textContent=v===1?"1 px (off)":v+" px";
  scheduleRender();
});
clusterSlider.addEventListener("input",function(){
  clusterValue.textContent=this.value+" px"; scheduleScan();
});
targetPicker.addEventListener("input",function(){
  var c=hex2rgb(this.value);
  targetRGB.value=c.join(",");
  targetDisp.textContent="RGB("+c.join(", ")+")";
  scheduleScan();
});
swatches.addEventListener("click",function(e){
  var sw=e.target.closest(".swatch");
  if(!sw||!sw.dataset.rgb) return;
  swatches.querySelectorAll(".swatch").forEach(function(s){s.classList.remove("active");});
  sw.classList.add("active");
  hlRGB.value=sw.dataset.rgb;
  var p=sw.dataset.rgb.split(",").map(Number);
  hlPicker.value=rgb2hex(p[0],p[1],p[2]);
  scheduleRender();
});
hlPicker.addEventListener("input",function(){
  var c=hex2rgb(this.value);
  hlRGB.value=c.join(",");
  swatches.querySelectorAll(".swatch").forEach(function(s){s.classList.remove("active");});
  scheduleRender();
});
cycleColours.addEventListener("change",function(){
  cycleFrame=0;
  if(this.checked) startColourCycle();
  else stopColourCycle();
  scheduleRender();
});
cycleSpeed.addEventListener("input",function(){
  cycleSpeedValue.textContent=this.value+" / 10";
  if(cycleColours.checked) startColourCycle();
});
modeBtns.addEventListener("click",function(e){
  var btn=e.target.closest(".mode-btn"); if(!btn) return;
  modeBtns.querySelectorAll(".mode-btn").forEach(function(b){b.classList.remove("active");});
  btn.classList.add("active");
  outMode.value=btn.dataset.mode;
  scheduleRender();
});

// === Image loading ===
function loadImageFile(file){
  var ok=["image/png","image/jpeg"];
  if(ok.indexOf(file.type)===-1&&!file.name.match(/\.(png|jpe?g)$/i)){
    showInfo("Unsupported file type: "+file.name+". Use a direct PNG or JPEG game screenshot.",true); return;
  }
  var reader=new FileReader();
  reader.onerror=function(){showInfo("Failed to read file.",true);};
  reader.onload=function(ev){
    var img=new Image();
    img.onerror=function(){showInfo("Failed to decode image.",true);};
    img.onload=function(){
      imgW=img.width; imgH=img.height;
      sourceCanvas.width=imgW; sourceCanvas.height=imgH;
      sourceCtx.drawImage(img,0,0);
      srcData=sourceCtx.getImageData(0,0,imgW,imgH);
      var mb=(file.size/1048576).toFixed(1);
      var isJ=/\.(jpe?g)$/i.test(file.name)||file.type==="image/jpeg";
      var info=file.name+" &mdash; "+imgW+" x "+imgH+" &mdash; "+mb+" MB";
      if(isJ) info+='<br><span class="warn">JPEG detected. Tolerance 5+ recommended.</span>';
      if(imgW*imgH>20000000) info+='<br><span class="warn">Large image. May take a moment.</span>';
      showInfo(info,false);
      viewerLayout.classList.remove("hidden");
      runScan();
    };
    img.src=ev.target.result;
  };
  reader.readAsDataURL(file);
}
function showInfo(h,err){
  imageInfo.innerHTML=h; imageInfo.classList.remove("hidden");
  imageInfo.style.borderColor=err?"#ff4444":"transparent";
}

dropZone.addEventListener("dragover",function(e){e.preventDefault();dropZone.classList.add("drag-over");});
dropZone.addEventListener("dragleave",function(){dropZone.classList.remove("drag-over");});
dropZone.addEventListener("drop",function(e){
  e.preventDefault();dropZone.classList.remove("drag-over");
  if(e.dataTransfer.files.length>0)loadImageFile(e.dataTransfer.files[0]);
});
dropZone.addEventListener("click",function(e){if(e.target.tagName!=="INPUT")fileInput.click();});
fileInput.addEventListener("change",function(){if(this.files.length>0)loadImageFile(this.files[0]);});

// === Debounced scan/render ===
function scheduleScan(){
  if(!srcData) return;
  clearTimeout(scanTimer);
  scanTimer=setTimeout(runScan,80);
}
function scheduleRender(){
  if(!rawMask) return;
  clearTimeout(scanTimer);
  scanTimer=setTimeout(function(){dilateAndRender();},30);
}
function startColourCycle(){
  stopColourCycle();
  cycleTimer=setInterval(function(){
    if(!rawMask||document.hidden) return;
    cycleFrame=(cycleFrame+1)%CYCLE_COLOURS.length;
    renderCycleFrame();
  },getCycleDelay());
}
function getCycleDelay(){
  return Math.max(100,950-(parseInt(cycleSpeed.value,10)*100));
}
function stopColourCycle(){
  if(cycleTimer!==null){clearInterval(cycleTimer);cycleTimer=null;}
}
function renderCycleFrame(){
  if(!dilatedMask) return;
  renderOutput(dilatedMask,getSettings());
  applyZoom();
}
document.addEventListener("visibilitychange",function(){
  if(!document.hidden&&cycleColours.checked) renderCycleFrame();
});

// === Core scan ===
function runScan(){
  if(!srcData) return;
  var s=getSettings();
  var data=srcData.data, total=imgW*imgH;
  var mask=new Uint8Array(total);
  var count=0;
  for(var i=0;i<total;i++){
    var o=i*4;
    if(Math.abs(data[o]-s.tR)<=s.tol&&Math.abs(data[o+1]-s.tG)<=s.tol&&Math.abs(data[o+2]-s.tB)<=s.tol){
      mask[i]=1; count++;
    }
  }
  // Cluster filter
  if(s.minCluster>1){
    mask=filterClusters(mask,imgW,imgH,s.minCluster);
    count=0; for(var j=0;j<total;j++){if(mask[j])count++;}
  }
  rawMask=mask;
  // Stats
  var pct=total>0?((count/total)*100).toFixed(3):"0";
  statsEl.innerHTML='<span class="stat-value">'+fmt(count)+'</span> px matched ('+pct+'%)';
  dilateAndRender();
  downloadBtn.disabled=false;
}

function filterClusters(mask,w,h,min){
  var total=w*h, labels=new Int32Array(total), nl=1, sizes=[0];
  for(var i=0;i<total;i++){
    if(!mask[i]||labels[i]) continue;
    var q=[i]; labels[i]=nl; var sz=0,hd=0;
    while(hd<q.length){
      var idx=q[hd++]; sz++;
      var x=idx%w,y=(idx-x)/w;
      for(var dy=-1;dy<=1;dy++){for(var dx=-1;dx<=1;dx++){
        if(!dx&&!dy) continue;
        var nx=x+dx,ny=y+dy;
        if(nx<0||nx>=w||ny<0||ny>=h) continue;
        var ni=ny*w+nx;
        if(mask[ni]&&!labels[ni]){labels[ni]=nl;q.push(ni);}
      }}
    }
    sizes.push(sz); nl++;
  }
  var out=new Uint8Array(total);
  for(var k=0;k<total;k++){if(labels[k]>0&&sizes[labels[k]]>=min)out[k]=1;}
  return out;
}

// === Dilation (thickness) ===
function dilateMask(mask,w,h,radius){
  if(radius<=1) return mask;
  var out=new Uint8Array(w*h);
  var r=radius-1;
  for(var i=0;i<w*h;i++){
    if(!mask[i]) continue;
    var cx=i%w, cy=(i-cx)/w;
    var y0=Math.max(0,cy-r), y1=Math.min(h-1,cy+r);
    var x0=Math.max(0,cx-r), x1=Math.min(w-1,cx+r);
    var r2=r*r;
    for(var py=y0;py<=y1;py++){
      for(var px=x0;px<=x1;px++){
        var ddx=px-cx, ddy=py-cy;
        if(ddx*ddx+ddy*ddy<=r2) out[py*w+px]=1;
      }
    }
  }
  return out;
}

function dilateAndRender(){
  var s=getSettings();
  dilatedMask=dilateMask(rawMask,imgW,imgH,s.thickness);
  renderOutput(dilatedMask,s);
  applyZoom();
}

// === Render output ===
function renderOutput(mask,s){
  outCanvas.width=imgW; outCanvas.height=imgH;
  var imgd=outCtx.createImageData(imgW,imgH);
  var d=imgd.data, src=srcData.data, total=imgW*imgH;
  var hR=s.hR,hG=s.hG,hB=s.hB,m=s.mode;
  for(var i=0;i<total;i++){
    var o=i*4;
    if(m==="overlay"){
      if(mask[i]){d[o]=hR;d[o+1]=hG;d[o+2]=hB;}
      else{d[o]=src[o];d[o+1]=src[o+1];d[o+2]=src[o+2];}
      d[o+3]=255;
    }else if(m==="black"){
      if(mask[i]){d[o]=hR;d[o+1]=hG;d[o+2]=hB;}
      d[o+3]=255;
    }else{
      if(mask[i]){d[o]=hR;d[o+1]=hG;d[o+2]=hB;d[o+3]=255;}
    }
  }
  outCtx.putImageData(imgd,0,0);
}

// === Zoom & Pan ===
function applyZoom(){
  outCanvas.style.transform="translate("+panX+"px,"+panY+"px) scale("+zoomScale+")";
  zoomSpan.textContent=Math.round(zoomScale*100)+"%";
}
function zoomFit(){
  if(!imgW||!imgH) return;
  var cw=viewer.clientWidth,ch=viewer.clientHeight;
  zoomScale=Math.min(cw/imgW,ch/imgH,1);
  panX=(cw-imgW*zoomScale)/2; panY=(ch-imgH*zoomScale)/2;
  applyZoom();
}
function zoomTo(ns,cx,cy){
  ns=Math.max(0.05,Math.min(30,ns));
  var ix=(cx-panX)/zoomScale,iy=(cy-panY)/zoomScale;
  zoomScale=ns; panX=cx-ix*zoomScale; panY=cy-iy*zoomScale;
  applyZoom();
}
viewer.addEventListener("wheel",function(e){
  e.preventDefault();
  var r=viewer.getBoundingClientRect();
  zoomTo(zoomScale*(e.deltaY<0?1.15:1/1.15),e.clientX-r.left,e.clientY-r.top);
},{passive:false});
viewer.addEventListener("mousedown",function(e){
  if(e.button!==0) return;
  isPanning=true;psx=e.clientX;psy=e.clientY;ppx=panX;ppy=panY;e.preventDefault();
});
window.addEventListener("mousemove",function(e){
  if(!isPanning) return;
  panX=ppx+(e.clientX-psx);panY=ppy+(e.clientY-psy);applyZoom();
});
window.addEventListener("mouseup",function(){isPanning=false;});
var ts={};
viewer.addEventListener("touchstart",function(e){
  if(e.touches.length===1){ts.x=e.touches[0].clientX;ts.y=e.touches[0].clientY;ts.px=panX;ts.py=panY;}
},{passive:true});
viewer.addEventListener("touchmove",function(e){
  if(e.touches.length===1){panX=ts.px+(e.touches[0].clientX-ts.x);panY=ts.py+(e.touches[0].clientY-ts.y);applyZoom();e.preventDefault();}
},{passive:false});
zoomInBtn.addEventListener("click",function(){var r=viewer.getBoundingClientRect();zoomTo(zoomScale*1.4,r.width/2,r.height/2);});
zoomOutBtn.addEventListener("click",function(){var r=viewer.getBoundingClientRect();zoomTo(zoomScale/1.4,r.width/2,r.height/2);});
zoomFitBtn.addEventListener("click",zoomFit);
zoom100Btn.addEventListener("click",function(){var r=viewer.getBoundingClientRect();zoomTo(1,r.width/2,r.height/2);});

// Auto-fit on window resize
window.addEventListener("resize",function(){if(srcData)zoomFit();});

// === Download ===
downloadBtn.addEventListener("click",function(){
  if(!rawMask) return;
  var m=dlMode.value;
  if(m==="all"){dlAs("overlay");setTimeout(function(){dlAs("black");},300);setTimeout(function(){dlAs("transparent");},600);}
  else if(m==="current"){dlAs(outMode.value);}
  else{dlAs(m);}
});
function dlAs(mode){
  var s=getSettings(); s.mode=mode;
  var tc=document.createElement("canvas"); tc.width=imgW; tc.height=imgH;
  var mask=dilateMask(rawMask,imgW,imgH,s.thickness);
  var tctx=tc.getContext("2d");
  var id=tctx.createImageData(imgW,imgH), d=id.data, src=srcData.data, total=imgW*imgH;
  var hR=s.hR,hG=s.hG,hB=s.hB;
  for(var i=0;i<total;i++){
    var o=i*4;
    if(mode==="overlay"){
      if(mask[i]){d[o]=hR;d[o+1]=hG;d[o+2]=hB;}
      else{d[o]=src[o];d[o+1]=src[o+1];d[o+2]=src[o+2];}
      d[o+3]=255;
    }else if(mode==="black"){
      if(mask[i]){d[o]=hR;d[o+1]=hG;d[o+2]=hB;} d[o+3]=255;
    }else{
      if(mask[i]){d[o]=hR;d[o+1]=hG;d[o+2]=hB;d[o+3]=255;}
    }
  }
  tctx.putImageData(id,0,0);
  var link=document.createElement("a");
  link.download="fh_road_finder_tol"+s.tol+"_"+mode+".png";
  link.href=tc.toDataURL("image/png");
  document.body.appendChild(link);link.click();document.body.removeChild(link);
}

// === Reset ===
resetBtn.addEventListener("click",function(){
  srcData=null;rawMask=null;dilatedMask=null;imgW=0;imgH=0;
  viewerLayout.classList.add("hidden");
  imageInfo.classList.add("hidden");imageInfo.innerHTML="";
  downloadBtn.disabled=true;statsEl.innerHTML="";
  fileInput.value="";zoomScale=1;panX=0;panY=0;
});
if(cycleColours.checked) startColourCycle();
})();
