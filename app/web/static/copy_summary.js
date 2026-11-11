// "Copy summary" (#2162): put the text on the clipboard; with no Clipboard API, show the text selected. No dialog (P6).
(function () {
  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-copy-summary]");
    if (!button) return;
    var section = button.closest("#trip-summary");  // the current section: an htmx swap replaces it
    var box = section.querySelector("textarea");
    var status = section.querySelector("[role=status]");
    function showBox() {
      box.hidden = false;
      box.focus();
      box.select();
      status.textContent = "Select the text and copy it";
    }
    if (!navigator.clipboard || !navigator.clipboard.writeText) {
      showBox();
      return;
    }
    navigator.clipboard.writeText(box.value).then(function () {
      status.textContent = "Copied";
    }, showBox);
  });
})();
