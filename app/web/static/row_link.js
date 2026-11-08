// A link to #it-<id> opens the row of that itinerary and its "Legs and fares" detail (#814).
(function () {
  function openRowOfHash() {
    var id = decodeURIComponent(location.hash.slice(1));
    if (!/^it-\d+$/.test(id)) return;
    var row = document.getElementById(id);
    if (!row) return;
    var detail = row.nextElementSibling;
    if (detail && detail.matches("tr.detail")) {
      var box = detail.querySelector("details");
      if (box) box.open = true;
    }
    row.scrollIntoView({ block: "start" });
  }
  window.addEventListener("hashchange", openRowOfHash);
  openRowOfHash();
})();
