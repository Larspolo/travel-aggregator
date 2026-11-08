// The import page (#777): when the owner selects an export file, preselect the trip of the same title, origin,
// destination and dates, so that a second import of the file goes into the same trip and makes no duplicate.
(function () {
  const file = document.getElementById("i-file");
  const target = document.getElementById("i-target");
  if (!file || !target) return;
  file.addEventListener("change", async function () {
    if (!file.files.length) return;
    let t;
    try { t = JSON.parse(await file.files[0].text()).trip; } catch (e) { return; }
    if (!t) return;
    const key = JSON.stringify([t.title ?? null, t.origin || null, t.destination || null,
                                t.date_from ?? null, t.date_to ?? null]);
    const option = Array.from(target.options).find(function (o) { return o.dataset.match === key; });
    target.value = option ? option.value : "";
  });
})();
