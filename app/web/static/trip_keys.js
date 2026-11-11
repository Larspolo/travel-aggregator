// j and k move the focus between the rows of the trip page, Enter opens or closes the details of the row (#2437).
document.addEventListener("keydown", function (e) {
  var t = e.target;
  if (e.ctrlKey || e.altKey || e.metaKey) return;
  if (t && (t.isContentEditable || /^(INPUT|SELECT|TEXTAREA)$/.test(t.tagName))) return;
  var rows = Array.prototype.slice.call(document.querySelectorAll('tr[id^="it-"]'));  // read at each key: htmx swaps #table
  var i = rows.indexOf(document.activeElement);
  if (e.key === "j" || e.key === "k") {
    var next = i < 0 ? (e.key === "j" ? 0 : rows.length - 1) : i + (e.key === "j" ? 1 : -1);
    if (next < 0 || next >= rows.length) return;
    e.preventDefault();
    rows[next].tabIndex = -1;  // in the script, not the template: the tests read <tr id="it-N"> (#2437)
    rows[next].focus();
  } else if (e.key === "Enter" && i >= 0) {
    var detail = rows[i].nextElementSibling;
    var d = detail && detail.classList.contains("detail") ? detail.querySelector("details") : null;
    if (!d) return;
    e.preventDefault();
    d.open = !d.open;
  }
});
