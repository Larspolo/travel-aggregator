// "Log in with a passkey" on the login page (#1559): get the options, call navigator.credentials.get() and post it.
(() => {
  const box = document.getElementById("passkey-login");
  if (!box) return;
  const button = document.getElementById("passkey-login-button");
  const status = document.getElementById("passkey-login-status");
  const say = (text) => { status.textContent = text; status.hidden = !text; };
  const post = (url, body) => fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": box.dataset.csrf },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const answer = async (response) => {
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "The server answered " + response.status + ".");
    return data;
  };

  if (!window.PublicKeyCredential || !PublicKeyCredential.parseRequestOptionsFromJSON) {
    button.disabled = true;
    say("This browser has no passkeys. Log in with the password.");
    return;
  }

  button.addEventListener("click", async () => {
    say("");
    button.disabled = true;
    try {
      const publicKey = PublicKeyCredential.parseRequestOptionsFromJSON(await answer(await post("/login/passkey/options")));
      const credential = await navigator.credentials.get({ publicKey });
      const done = await answer(await post("/login/passkey", credential.toJSON()));
      window.location.assign(done.next || "/");
    } catch (e) {
      say(e.name === "NotAllowedError" ? "The passkey login stopped. Try again, or log in with the password."
        : e.message);
      button.disabled = false;
    }
  });
})();
