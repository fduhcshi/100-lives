"use strict";
(function () {
  var button = document.getElementById("submit-btn");
  button.disabled = true;
  button.textContent = "静态展示页 · 无法运行模拟";
  document.getElementById("fill-sample").addEventListener("click", function () {
    document.getElementById("profile").value = "我 30 岁，正考虑是否换城市工作。新机会薪资更高，但也意味着离开熟悉的生活环境。我在意职业成长、存款和亲密关系。";
    document.getElementById("choice-a").value = "留在当前城市";
    document.getElementById("choice-b").value = "去新城市接受工作";
    document.getElementById("char-count").textContent = document.getElementById("profile").value.length;
  });
})();
