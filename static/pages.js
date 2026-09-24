"use strict";
(function () {
  var note = document.getElementById("mode-note");
  note.textContent = "这是 GitHub Pages 静态展示页。生成平行人生请使用 ";
  var link = document.createElement("a");
  link.href = "https://one-hundred-lives.fduhcshi.workers.dev/";
  link.textContent = "Cloudflare 在线版";
  note.appendChild(link);
  note.appendChild(document.createTextNode("（需要访问密码），或在本地运行项目。"));
  note.style.display = "block";
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
