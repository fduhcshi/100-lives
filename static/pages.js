"use strict";
(function () {
  var button = document.getElementById("submit-btn");
  button.disabled = true;
  button.textContent = "静态展示页 · 无法运行模拟";
  document.getElementById("fill-sample").addEventListener("click", function () {
    document.getElementById("profile").value = "想在闲暇时间培养一项可以长期坚持的爱好。每周有一个下午可以投入，预算适中；希望享受创作过程，也愿意认识有共同兴趣的人。";
    document.getElementById("choice-a").value = "每周参加陶艺课，练习手作";
    document.getElementById("choice-b").value = "学习摄影，记录日常与自然";
    document.getElementById("char-count").textContent = document.getElementById("profile").value.length;
  });
})();
