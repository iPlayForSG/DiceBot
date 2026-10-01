"use strict";

window.tabletopArtReady = fetch("./public/assets/table-art.json").then(response => {
  if (!response.ok) throw new Error("桌面图包加载失败，请刷新页面。");
  return response.json();
});

// Card text is readable on mobile too: click or focus a face to open the original image.
function openTabletopCard(element) {
  const dialog = document.getElementById("card-dialog");
  document.getElementById("card-title").textContent = element.alt || "卡牌";
  const image = document.getElementById("card-full");
  image.src = element.src;
  image.alt = element.alt || "卡牌大图";
  if (!dialog.open) dialog.showModal();
}
document.addEventListener("click", event => {
  const target = event.target.closest("img[data-card-preview]");
  if (target && !target.closest("button[data-action]")) openTabletopCard(target);
});
document.addEventListener("keydown", event => {
  if (["Enter", " "].includes(event.key) && event.target.matches("img[data-card-preview]")) {
    event.preventDefault();
    openTabletopCard(event.target);
  }
});
