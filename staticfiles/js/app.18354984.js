(function(t){function e(e){for(var i,o,r=e[0],c=e[1],u=e[2],d=0,p=[];d<r.length;d++)o=r[d],Object.prototype.hasOwnProperty.call(n,o)&&n[o]&&p.push(n[o][0]),n[o]=0;for(i in c)Object.prototype.hasOwnProperty.call(c,i)&&(t[i]=c[i]);l&&l(e);while(p.length)p.shift()();return s.push.apply(s,u||[]),a()}function a(){for(var t,e=0;e<s.length;e++){for(var a=s[e],i=!0,r=1;r<a.length;r++){var c=a[r];0!==n[c]&&(i=!1)}i&&(s.splice(e--,1),t=o(o.s=a[0]))}return t}var i={},n={app:0},s=[];function o(e){if(i[e])return i[e].exports;var a=i[e]={i:e,l:!1,exports:{}};return t[e].call(a.exports,a,a.exports,o),a.l=!0,a.exports}o.m=t,o.c=i,o.d=function(t,e,a){o.o(t,e)||Object.defineProperty(t,e,{enumerable:!0,get:a})},o.r=function(t){"undefined"!==typeof Symbol&&Symbol.toStringTag&&Object.defineProperty(t,Symbol.toStringTag,{value:"Module"}),Object.defineProperty(t,"__esModule",{value:!0})},o.t=function(t,e){if(1&e&&(t=o(t)),8&e)return t;if(4&e&&"object"===typeof t&&t&&t.__esModule)return t;var a=Object.create(null);if(o.r(a),Object.defineProperty(a,"default",{enumerable:!0,value:t}),2&e&&"string"!=typeof t)for(var i in t)o.d(a,i,function(e){return t[e]}.bind(null,i));return a},o.n=function(t){var e=t&&t.__esModule?function(){return t["default"]}:function(){return t};return o.d(e,"a",e),e},o.o=function(t,e){return Object.prototype.hasOwnProperty.call(t,e)},o.p="/";var r=window["webpackJsonp"]=window["webpackJsonp"]||[],c=r.push.bind(r);r.push=e,r=r.slice();for(var u=0;u<r.length;u++)e(r[u]);var l=c;s.push([0,"chunk-vendors"]),a()})({0:function(t,e,a){t.exports=a("cd49")},"39d8":function(t,e,a){},"3b1b":function(t,e,a){},"3c14":function(t,e,a){},"41cf":function(t,e,a){"use strict";var i=a("d3e2"),n=a.n(i);n.a},4221:function(t,e,a){"use strict";var i=a("7b40"),n=a.n(i);n.a},"42e4":function(t,e,a){},"5c0b":function(t,e,a){"use strict";var i=a("9c0c"),n=a.n(i);n.a},"5f85":function(t,e,a){"use strict";var i=a("f763"),n=a.n(i);n.a},"630d":function(t,e,a){"use strict";var i=a("f789"),n=a.n(i);n.a},"7b40":function(t,e,a){},8917:function(t,e,a){"use strict";var i=a("39d8"),n=a.n(i);n.a},"8d5f":function(t,e,a){"use strict";var i=a("3c14"),n=a.n(i);n.a},"9c0c":function(t,e,a){},cd49:function(t,e,a){"use strict";a.r(e);a("e260"),a("e6cf"),a("cca6"),a("a79d"),a("3b1b"),a("d9f0");var i=a("2b0e"),n=function(){var t=this,e=t.$createElement,a=t._self._c||e;return a("div",{attrs:{id:"app"}},[a("router-view")],1)},s=[],o=(a("5c0b"),a("2877")),r={},c=Object(o["a"])(r,n,s,!1,null,null,null),u=c.exports,l=a("8c4f"),d=function(){var t=this,e=t.$createElement,a=t._self._c||e;return a("div",{staticClass:"home"},[a("h1",[t._v("Welcome to the Drug/Ampoule selection evaluator")]),a("p",[t._v(" This is some copy explaining why this is an important thing and the value of researching it and the methadology. ")]),a("h3",[t._v("How this works")]),a("p",[t._v("We collect:")]),t._m(0),a("div",[a("router-link",{staticClass:"btn btn-info",attrs:{to:"/session/new",tag:"button"}},[t._v("Get Started")])],1)])},p=[function(){var t=this,e=t.$createElement,a=t._self._c||e;return a("ul",[a("li",[t._v("Age range")]),a("li",[t._v("Speciality")]),a("li",[t._v("Grade/Years of experience")])])}],m=a("d4ec"),f=a("262e"),h=a("2caf"),v=a("9ab4"),b=a("60a3"),g=function(t){Object(f["a"])(a,t);var e=Object(h["a"])(a);function a(){return Object(m["a"])(this,a),e.apply(this,arguments)}return a}(b["c"]);g=Object(v["a"])([b["a"]],g);var y=g,O=y,j=(a("630d"),Object(o["a"])(O,d,p,!1,null,"5a54effd",null)),_=j.exports,C=function(){var t=this,e=t.$createElement,a=t._self._c||e;return a("div",{staticClass:"start"},[a("div",[a("vue-form-generator",{attrs:{schema:t.schema,model:t.model,options:t.formOptions}}),a("router-link",{staticClass:"btn btn-success",attrs:{to:"/session/1",tag:"button"}},[t._v("Start")])],1)])},S=[],k=a("4309"),L=a.n(k),w=(a("92bd"),function(t){Object(f["a"])(a,t);var e=Object(h["a"])(a);function a(){var t;return Object(m["a"])(this,a),t=e.apply(this,arguments),t.model={years:"",speciality:"",email:""},t.schema={fields:[{type:"input",inputType:"Number",label:"Years of Experience",model:"years",required:!0,validator:"integer"},{type:"select",label:"Speciality",model:"speciality",values:[{name:"Anaesthetics",id:"GAS"},{name:"Emergency Medicine",id:"A+E"},{name:"Intensive Care",id:"ICM"},{name:"Other",id:"OTH"}],required:!0},{type:"input",inputType:"email",label:"E-mail",model:"email",placeholder:"E-mail address",validator:"email"}]},t.formOptions={validateAfterLoad:!0,validateAfterChanged:!0,validateAsync:!0},t}return a}(b["c"]));w=Object(v["a"])([Object(b["a"])({components:{"vue-form-generator":L.a.component}})],w);var D=w,T=D,x=(a("8917"),Object(o["a"])(T,C,S,!1,null,null,null)),A=x.exports,I=function(){var t=this,e=t.$createElement,a=t._self._c||e;return a("div",{staticClass:"session"},[a("div",{staticClass:"controls"},[a("ProgressBar",{attrs:{done:this.sequence,total:100}}),a("button",{staticClass:"btn btn-info",staticStyle:{width:"131px"},on:{click:t.doPause}},[t._v(" "+t._s(t.paused?"Resume ▶️":"Pause ⏸")+" ")]),a("router-link",{staticClass:"btn btn-danger",attrs:{to:"/",tag:"button"}},[t._v("Quit")])],1),a("transition",{attrs:{name:"slide",mode:"out-in"}},[a("RunSet",{key:this.baseData.SetId,attrs:{setData:this.baseData},on:{setResult:t.handleResult}})],1)],1)},P=[],$=(a("d3b7"),a("bee2")),E=function(){var t=this,e=t.$createElement,a=t._self._c||e;return a("div",{staticClass:"study"},[""!=t.setData.TargetDrug?a("h1",[t._v(" Please select: "),a("span",[t._v(t._s(t.setData.TargetDrug.toUpperCase()))])]):a("h1"),a("div",{staticClass:"ampoules"},t._l(t.setData.Ampoules,(function(e){return a("Ampoule",{key:e.Id,attrs:{id:e.Id,src:e.ImageSrc,active:t.active},on:{loaded:t.imgLoaded,selected:t.selectAmpoule}})})),1),t.timeLimit>0?a("CountDown",{attrs:{timeLimit:t.timeLimit,timeLeft:t.timeLeft}}):t._e()],1)},R=[],M=function(){var t=this,e=t.$createElement,a=t._self._c||e;return a("div",{staticClass:"timer"},[a("svg",{attrs:{viewBox:"0 0 100 100",xmlns:"http://www.w3.org/2000/svg"}},[a("g",{staticClass:"circle"},[a("circle",{staticClass:"elapsed",attrs:{cx:"50",cy:"50",r:"45"}}),a("path",{staticClass:"remaining",class:t.animationColour,attrs:{"stroke-dasharray":t.animationFraction,d:"\n        M 50, 50\n        m -45, 0\n        a 45,45 0 1,0 90,0\n        a 45,45 0 1,0 -90,0\n      "}})])]),a("span",{staticClass:"label"},[t._v(t._s(t.timeLeftString))])])},q=[],G=(a("b680"),function(t){Object(f["a"])(a,t);var e=Object(h["a"])(a);function a(){return Object(m["a"])(this,a),e.apply(this,arguments)}return Object($["a"])(a,[{key:"timeLeftString",get:function(){return this.timeLeft<=0?"0.000":this.timeLeft.toFixed(3)}},{key:"animationFraction",get:function(){var t=1e3*this.timeLeft,e=t/this.timeLimit;return t<=0?"283":283*(e-1/this.timeLimit*(1-e))+" 283"}},{key:"animationColour",get:function(){var t=this.timeLeft;return t>2?"green":t>1?"orange":"red"}}]),a}(b["c"]));Object(v["a"])([Object(b["b"])()],G.prototype,"timeLimit",void 0),Object(v["a"])([Object(b["b"])()],G.prototype,"timeLeft",void 0),G=Object(v["a"])([b["a"]],G);var B=G,F=B,H=(a("4221"),Object(o["a"])(F,M,q,!1,null,"438c8229",null)),J=H.exports,N=function(){var t=this,e=t.$createElement,a=t._self._c||e;return a("div",{staticClass:"ampoule",class:{loading:t.loading,selected:t.selected,active:t.active},on:{click:t.click}},[t.loading?a("div",{staticClass:"lds-dual-ring"}):t._e(),a("img",{class:{active:t.active,selected:t.selected},attrs:{src:t.src},on:{load:t.onImgLoad}})])},W=[],Y=function(t){Object(f["a"])(a,t);var e=Object(h["a"])(a);function a(){var t;return Object(m["a"])(this,a),t=e.apply(this,arguments),t.loading=!0,t.selected=!1,t}return Object($["a"])(a,[{key:"onImgLoad",value:function(){this.$emit("loaded",this.id),this.loading=!1}},{key:"click",value:function(){this.active&&(this.$emit("selected",this.id),this.selected=!0)}}]),a}(b["c"]);Object(v["a"])([Object(b["b"])()],Y.prototype,"id",void 0),Object(v["a"])([Object(b["b"])()],Y.prototype,"src",void 0),Object(v["a"])([Object(b["b"])()],Y.prototype,"active",void 0),Y=Object(v["a"])([b["a"]],Y);var Q=Y,U=Q,z=(a("8d5f"),Object(o["a"])(U,N,W,!1,null,"5f54401e",null)),K=z.exports,V=function(t){Object(f["a"])(a,t);var e=Object(h["a"])(a);function a(){var t;return Object(m["a"])(this,a),t=e.apply(this,arguments),t.loading=!0,t.active=!1,t.imgCount=0,t.timeLimit=0,t.startTime=0,t.timeLeft=0,t.tick=0,t}return Object($["a"])(a,[{key:"beforeMount",value:function(){this.timeLimit=this.setData.TimeLimit,this.timeLeft=this.timeLimit/1e3}},{key:"startTimer",value:function(t){var e=this;this.timeLimit=t,this.startTime=(new Date).getTime(),this.timeLeft=this.timeLimit/1e3,this.tick=setInterval((function(){e.updateCountDown()}),25)}},{key:"updateCountDown",value:function(){var t=this.startTime+this.timeLimit-(new Date).getTime();this.timeLeft=t/1e3,t<0&&(this.active=!1,this.selectAmpoule(""),clearInterval(this.tick))}},{key:"imgLoaded",value:function(){var t=this;this.imgCount++,this.imgCount===this.setData.Ampoules.length&&setTimeout((function(){t.loading=!1,t.active=!0,t.startTimer(t.setData.TimeLimit),t.imgCount=0}),1e3)}},{key:"selectAmpoule",value:function(t){clearInterval(this.tick),this.active=!1;var e={SetId:this.setData.SetId,SelectedAmpoule:t,Time:this.timeLimit-1e3*this.timeLeft};this.$emit("setResult",e)}}]),a}(b["c"]);Object(v["a"])([Object(b["b"])()],V.prototype,"setData",void 0),V=Object(v["a"])([Object(b["a"])({components:{CountDown:J,Ampoule:K}})],V);var X=V,Z=X,tt=(a("41cf"),Object(o["a"])(Z,E,R,!1,null,"eaf103d8",null)),et=tt.exports,at=function(){var t=this,e=t.$createElement,a=t._self._c||e;return a("div",{staticClass:"progress"},[a("span",{staticClass:"label"},[t._v(t._s(t.done)+"/"+t._s(t.total))]),a("div",{staticClass:"outer"},[a("div",{staticClass:"bar",style:{width:t.percent+"%"}})])])},it=[],nt=function(t){Object(f["a"])(a,t);var e=Object(h["a"])(a);function a(){return Object(m["a"])(this,a),e.apply(this,arguments)}return Object($["a"])(a,[{key:"percent",get:function(){return Math.round(this.done/this.total*100)}}]),a}(b["c"]);Object(v["a"])([Object(b["b"])()],nt.prototype,"done",void 0),Object(v["a"])([Object(b["b"])()],nt.prototype,"total",void 0),nt=Object(v["a"])([b["a"]],nt);var st=nt,ot=st,rt=(a("5f85"),Object(o["a"])(ot,at,it,!1,null,"483287a6",null)),ct=rt.exports,ut=function(t){Object(f["a"])(a,t);var e=Object(h["a"])(a);function a(){var t;return Object(m["a"])(this,a),t=e.apply(this,arguments),t.baseData={SetId:"",TargetDrug:"",TimeLimit:0,Ampoules:[]},t.sequence=0,t.loading=!0,t.paused=!1,t}return Object($["a"])(a,[{key:"beforeMount",value:function(){this.getRemote()}},{key:"doPause",value:function(){this.paused=!this.paused,this.baseData={SetId:"",TargetDrug:"",TimeLimit:0,Ampoules:[]}}},{key:"onPauseStateChange",value:function(){this.paused||this.getRemote()}},{key:"handleResult",value:function(t){t.SessionId=this.$route.params.SessionId,t.Sequence=this.sequence,t.Correct=this.baseData.TargetDrug===t.SelectedAmpoule;var e={set_id:t.SetId,time:t.Time,correct:t.Correct,sequence_id:t.Sequence,session_id:t.SessionId,group:this.baseData.Group};""!==t.SelectedAmpoule&&(e.selected=t.SelectedAmpoule),console.log(e),fetch("https://mysterious-taiga-04569.herokuapp.com/results/",{method:"post",headers:{Accept:"application/json, text/plain, */*","Content-Type":"application/json"},body:JSON.stringify(e)}).then((function(t){return t.json()})).then((function(t){return console.log(t)})),this.paused||this.getRemote(),this.sequence++,console.log(t)}},{key:"getRemote",value:function(){var t=this;return this.loading=!0,new Promise((function(e,a){fetch("https://mysterious-taiga-04569.herokuapp.com/getdrugs/?format=json&session_id="+t.$route.params.SessionId).then((function(t){return t.json()})).then((function(a){t.baseData=a,t.loading=!1,e()})).catch((function(t){a(t)}))}))}}]),a}(b["c"]);Object(v["a"])([Object(b["d"])("paused")],ut.prototype,"onPauseStateChange",null),ut=Object(v["a"])([Object(b["a"])({components:{RunSet:et,ProgressBar:ct}})],ut);var lt=ut,dt=lt,pt=(a("d92a"),Object(o["a"])(dt,I,P,!1,null,"d332c620",null)),mt=pt.exports;i["a"].use(l["a"]);var ft=[{path:"/",name:"Home",component:_},{path:"/session/new",name:"Start",component:A},{path:"/session/:SessionId",name:"Run Test",component:mt}],ht=new l["a"]({mode:"history",base:"/",routes:ft}),vt=ht;i["a"].config.productionTip=!1,new i["a"]({router:vt,render:function(t){return t(u)}}).$mount("#app")},d3e2:function(t,e,a){},d92a:function(t,e,a){"use strict";var i=a("42e4"),n=a.n(i);n.a},d9f0:function(t,e,a){},f763:function(t,e,a){},f789:function(t,e,a){}});
//# sourceMappingURL=app.18354984.js.map