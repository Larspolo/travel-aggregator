// Add a passkey on the settings page (#1558): get the options, call navigator.credentials.create() and post the result.
(() => {
  const box = document.getElementById("passkeys");
  if (!box) return;
  const form = document.getElementById("passkey-add");
  const status = document.getElementById("passkey-status");
  const say = (text) => { status.textContent = text; };
  const post = (url, body) => fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": box.dataset.csrf },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (!window.PublicKeyCredential || !PublicKeyCredential.parseCreationOptionsFromJSON) {
    form.querySelector("button").disabled = true;
    say("This browser has no passkeys.");
    return;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = form.elements.name.value.trim();
    say("Wait…");
    try {
      const options = await post("/settings/passkeys/options");
      if (!options.ok) throw new Error("the server answered " + options.status);
      const publicKey = PublicKeyCredential.parseCreationOptionsFromJSON(await options.json());
      const credential = await navigator.credentials.create({ publicKey });
      const added = await post("/settings/passkeys", { name, credential: credential.toJSON() });
      if (!added.ok) throw new Error((await added.json()).error || "the server answered " + added.status);
      window.location.assign("/settings#passkeys");
      window.location.reload();
    } catch (e) {
      say("The passkey is not added: " + e.message);
    }
  });
})();
