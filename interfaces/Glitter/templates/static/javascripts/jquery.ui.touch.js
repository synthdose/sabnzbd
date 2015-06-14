/**
* jQuery.UI.TouchPlugin
* Copyright (c) 2010 Stephen von Takach
* licensed under MIT.
* Date: 27/8/2010
*
* Project Home: 
* http://code.google.com/p/jquery-ui-for--and-iphone/
*/
function cancelTap(){tapValid=!1}function cancelHold(){rightClickPending&&(window.clearTimeout(holdTimeout),rightClickPending=!1,rightClickEvent=null)}function startHold(e){rightClickPending||(rightClickPending=!0,rightClickEvent=e.changedTouches[0],holdTimeout=window.setTimeout("doRightClick();",800))}function doRightClick(){rightClickPending=!1;var e=rightClickEvent,t=document.createEvent("MouseEvent");t.initMouseEvent("mouseup",!0,!0,window,1,e.screenX,e.screenY,e.clientX,e.clientY,!1,!1,!1,!1,0,null),e.target.dispatchEvent(t),t=document.createEvent("MouseEvent"),t.initMouseEvent("mousedown",!0,!0,window,1,e.screenX,e.screenY,e.clientX,e.clientY,!1,!1,!1,!1,2,null),e.target.dispatchEvent(t),t=document.createEvent("MouseEvent"),t.initMouseEvent("contextmenu",!0,!0,window,1,e.screenX+50,e.screenY+5,e.clientX+50,e.clientY+5,!1,!1,!1,!1,2,null),e.target.dispatchEvent(t),cancelMouseUp=!0,rightClickEvent=null}function TouchStart(e){var t=e.changedTouches,n=t[0],c="mouseover",i=document.createEvent("MouseEvent");i.initMouseEvent(c,!0,!0,window,1,n.screenX,n.screenY,n.clientX,n.clientY,!1,!1,!1,!1,0,null),n.target.dispatchEvent(i),c="mousedown",i=document.createEvent("MouseEvent"),i.initMouseEvent(c,!0,!0,window,1,n.screenX,n.screenY,n.clientX,n.clientY,!1,!1,!1,!1,0,null),n.target.dispatchEvent(i),tapValid?(window.clearTimeout(tapTimeout),n.target==lastTap?(lastTap=null,tapValid=!1,c="click",i=document.createEvent("MouseEvent"),i.initMouseEvent(c,!0,!0,window,1,n.screenX,n.screenY,n.clientX,n.clientY,!1,!1,!1,!1,0,null),n.target.dispatchEvent(i),c="dblclick",i=document.createEvent("MouseEvent"),i.initMouseEvent(c,!0,!0,window,1,n.screenX,n.screenY,n.clientX,n.clientY,!1,!1,!1,!1,0,null),n.target.dispatchEvent(i)):(lastTap=n.target,tapValid=!0,tapTimeout=window.setTimeout("cancelTap();",600),startHold(e))):(lastTap=n.target,tapValid=!0,tapTimeout=window.setTimeout("cancelTap();",600),startHold(e))}function TouchHandler(e){var t="",n=0;if(!(e.touches.length>1)){switch(e.type){case"touchstart":if($(e.changedTouches[0].target).is("select"))return;return TouchStart(e),e.preventDefault(),!1;case"touchmove":cancelHold(),t="mousemove",e.preventDefault();break;case"touchend":if(cancelMouseUp)return cancelMouseUp=!1,e.preventDefault(),!1;cancelHold(),t="mouseup";break;default:return}var c=e.changedTouches,i=c[0],o=document.createEvent("MouseEvent");o.initMouseEvent(t,!0,!0,window,1,i.screenX,i.screenY,i.clientX,i.clientY,!1,!1,!1,!1,n,null),i.target.dispatchEvent(o),"mouseup"==t&&tapValid&&i.target==lastTap&&(o=document.createEvent("MouseEvent"),o.initMouseEvent("click",!0,!0,window,1,i.screenX,i.screenY,i.clientX,i.clientY,!1,!1,!1,!1,n,null),i.target.dispatchEvent(o))}}$(function(){$.extend($.support,{touch:"ontouchend"in document}),$.support.touch&&(document.addEventListener("touchstart",TouchHandler,!1),document.addEventListener("touchmove",TouchHandler,!1),document.addEventListener("touchend",TouchHandler,!1),document.addEventListener("touchcancel",TouchHandler,!1))});var lastTap=null,tapValid=!1,tapTimeout=null,rightClickPending=!1,rightClickEvent=null,holdTimeout=null,cancelMouseUp=!1;


