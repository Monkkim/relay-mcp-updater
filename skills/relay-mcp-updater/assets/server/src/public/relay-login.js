import PocketBase, { BaseAuthStore } from '/assets/pocketbase.es.mjs';
import { normalizeAuthMethods } from '/assets/auth-methods.js';

const config = JSON.parse(document.getElementById('login-config').textContent);
const status = document.getElementById('status');
const container = document.getElementById('providers');
// Keep credentials in memory only, never in browser localStorage.
const pb = new PocketBase(config.authUrl, new BaseAuthStore());
pb.afterSend = (response, data) => response.url.includes('/auth-methods') ? normalizeAuthMethods(data) : data;
const showStatus = (message, error = false) => {
  status.textContent = message;
  status.className = error ? 'error' : '';
};

try {
  const methods = await pb.collection(config.collection).listAuthMethods();
  const providers = methods.oauth2.enabled ? methods.oauth2.providers : [];
  if (!providers.length) throw new Error('no providers');
  for (const provider of providers) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = `Continue with ${provider.displayName || provider.name}`;
    button.addEventListener('click', () => {
      // Open synchronously during the user click so browsers allow the popup.
      const popup = window.open('about:blank', '_blank', 'width=520,height=720');
      if (!popup) {
        showStatus('Allow pop-ups for this page, then try again.', true);
        return;
      }
      for (const item of container.querySelectorAll('button')) item.disabled = true;
      showStatus('Finish signing in in the new window…');
      const requestKey = `relay-login-${config.state}`;
      let finished = false;
      const timeout = setTimeout(() => pb.cancelRequest(requestKey), 10 * 60_000);
      const closed = setInterval(() => {
        if (popup.closed && !finished) pb.cancelRequest(requestKey);
      }, 500);
      pb.collection(config.collection).authWithOAuth2({
        provider: provider.name,
        requestKey,
        urlCallback: (url) => { popup.location.href = url; },
      }).then((auth) => {
        finished = true;
        showStatus('Connecting your Relay account…');
        // Native form navigation keeps authorization codes out of fetch redirects.
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = '/oauth/login';
        for (const [name, value] of Object.entries({state: config.state, pbToken: auth.token})) {
          const input = document.createElement('input');
          input.type = 'hidden'; input.name = name; input.value = value;
          form.appendChild(input);
        }
        document.body.appendChild(form);
        form.submit();
      }).catch(() => {
        showStatus('Sign-in was cancelled or could not finish. Please try again.', true);
        for (const item of container.querySelectorAll('button')) item.disabled = false;
      }).finally(() => {
        finished = true;
        clearTimeout(timeout); clearInterval(closed);
        popup.close(); pb.authStore.clear();
      });
    });
    container.appendChild(button);
  }
  if (!status.classList.contains('error')) showStatus('');
} catch {
  showStatus('Could not load Relay sign-in options. Reload this page to try again.', true);
}
