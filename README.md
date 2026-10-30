# React + Express + TypeScript

## Deploy on Vercel

1. Push this repository to GitHub, GitLab, or Bitbucket.
2. In Vercel, choose **Add New → Project** and import the repository.
3. Keep **Root Directory** at the repository root (`.`), then click **Deploy**.

The included `vercel.json` configures installation, the Vite build, frontend
routes, and the Express API. No environment variables or separate backend
deployment are needed. Use Node.js **24.x** if asked for a runtime version.

After deployment, open the site and `/api/hello` to verify the frontend and API.
Future pushes to the connected production branch deploy automatically.

Alternatively, run `npx vercel` from the repository root for a preview or
`npx vercel --prod` for production (sign in when prompted).

## Local development

Run `npm install` at the repository root, then run these in two terminals:

```sh
npm run dev:server
```

```sh
npm run dev
```

Open the URL printed by Vite. It proxies `/api` requests to port 5000 locally;
Vercel runs the same Express app as a function in production.

## Checks

```sh
npm run build
npm run lint
```

Vercel documentation: [Vite](https://vercel.com/docs/frameworks/frontend/vite)
and [Node.js functions](https://vercel.com/docs/functions/runtimes/node-js).
