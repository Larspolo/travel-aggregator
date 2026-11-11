// Escape closes the open menu (a <details>) and puts the focus back on its summary (#820).
document.addEventListener("keydown", function (e) {
  if (e.key !== "Escape") return;
  document.querySelectorAll("details.menu[open], details.more[open]").forEach(function (d) {
    d.open = false;
    d.querySelector("summary").focus();
  });
});
