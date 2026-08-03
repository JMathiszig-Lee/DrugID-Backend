# Ampoule study frontend

Vue 3 and Vite client for registration, magic-link verification, and the timed ampoule study.

## Local development

Use Node 24.15 or newer within Node 24, then install and run the client:

```sh
npm ci
cp .env.example .env
npm run dev
```

The browser always calls same-origin `/api/*` paths. During development Vite proxies those paths
to `DJANGO_API_TARGET`, which defaults to `http://127.0.0.1:8000`.

Run Django with `PUBLIC_APP_URL=http://localhost:5173`, include that origin in
`CSRF_TRUSTED_ORIGINS`, and set `SHOW_DEBUG_MAGIC_LINK=True` only if you want the local API
response to show the link without reading the console-email output.

## Checks

```sh
npm run check
```

This runs ESLint, Vitest, Vue TypeScript checking, and the production build. Production assets are
written to `dist/` with `/static/` URLs so Django can collect and serve them.

Magic-link tokens are expected in the URL fragment (`/verify#token=...`). The fragment is removed
before the token is exchanged for the secure study cookie. Tokens in query strings are deliberately
rejected because URLs can be retained in browser, proxy, and application logs.

## Tutorial and study results

Fresh participants must complete the server-assigned mixed-style tutorial before the real study
can begin. Tutorial trials use the same image-loading, viewport checks and timer as study trials,
but their requests use only `/api/study/tutorial/*` endpoints. A discriminated pending submission
survives refresh and preserves that separation: tutorial responses can never be retried through the
study-result endpoint.

After every practice response, the participant sees feedback and explicitly continues. After the
last practice trial, they explicitly leave the feedback screen and then select **Begin study**; the
first real trial is never started automatically. Practice progress is displayed separately and is
not included in study progress or study results.
