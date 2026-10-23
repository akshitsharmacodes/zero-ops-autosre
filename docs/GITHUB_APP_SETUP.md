# Connecting AutoSRE to GitHub (GitHub App)

AutoSRE opens pull requests as its **own robot**, `<your-app-name>[bot]`. It isn't you, and it can only touch the
repository you pick, with only the permissions below. Its access keys expire every hour and renew automatically.
Setup takes about 10 minutes and is done once.

> Without any of this, AutoSRE still works fully offline with the local "pretend GitHub" (`DELIVERY_PROVIDER=local`).

## Step 1: Create the victim repository on GitHub

1. github.com → **New repository** → name it `victim-service`. Public or private both work. **Don't** add a README, .gitignore or license, because it must start empty.
2. Push the seeded history to it from the project folder (replace `YOUR-USER`):

```bash
git -C var/victim_repo push https://github.com/YOUR-USER/victim-service.git main
```

3. Make a working clone that AutoSRE reads history from:

```bash
git clone https://github.com/YOUR-USER/victim-service.git var/victim_repo_github
```

## Step 2: Create the GitHub App

github.com → your profile picture → **Settings** → (bottom left) **Developer settings** → **GitHub Apps** → **New GitHub App**.

Fill in only these fields:

| Field | Value |
|---|---|
| GitHub App name | `AutoSRE Zero-Ops` (must be unique on GitHub; add your name if it's taken) |
| Homepage URL | `http://127.0.0.1:5173` |
| Callback URL | *leave empty* |
| Request user authorization (OAuth) during installation | **unticked** |
| Setup URL | `http://127.0.0.1:8000/api/v1/github/callback` |
| Redirect on update | **ticked** |
| Webhook → Active | **unticked** (AutoSRE checks the PR itself, so GitHub never needs to reach your laptop) |

**Repository permissions.** Leave everything else on "No access":

| Permission | Access | Why |
|---|---|---|
| Contents | Read and write | push the fix branch |
| Pull requests | Read and write | open the PR, comment, mark ready, label |
| Checks | Read-only | read CI results |
| Commit statuses | Read-only | read CI results |
| Metadata | Read-only | required by GitHub (set automatically) |

**Where can this GitHub App be installed?** Choose **Only on this account**. Then click **Create GitHub App**.

## Step 3: Get the App ID and private key

1. On the App's page, copy the **App ID** (a number near the top).
2. Scroll to **Private keys**, click **Generate a private key**, and a `.pem` file downloads.
3. Move it to `secrets/github-app.pem` inside the project. The `secrets/` folder and `*.pem` files are git-ignored, so they're never committed.

Treat the `.pem` like a password. Anyone who has it can act as the App on the repositories it's installed on.

## Step 4: Tell AutoSRE (`.env`)

```ini
DELIVERY_PROVIDER=github
GITHUB_REPO=YOUR-USER/victim-service
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY_PATH=secrets/github-app.pem
TARGET_REPO_PATH=var/victim_repo_github
```

Restart the backend (`python scripts/dev.py`).

## Step 5: Install it (the "Connect GitHub" button)

1. Dashboard → **Controls** → **3 · GitHub** → **Connect GitHub**.
2. GitHub asks where to install it. Choose **Only select repositories**, pick `victim-service`, and click **Install**.
3. You're sent back to the dashboard with a "GitHub connected" message. The panel now shows `Connected to YOUR-USER/victim-service as autosre-zero-ops[bot]`.

You can also check from the terminal:

```bash
curl http://127.0.0.1:8000/api/v1/github/status
```

## Removing access

- Dashboard → **Disconnect** makes AutoSRE forget the installation.
- To fully revoke it: GitHub → Settings → **Applications** → **Installed GitHub Apps** → AutoSRE → **Uninstall**.
- If the `.pem` ever leaks: App settings → Private keys → **Delete** it and generate a new one.

## Troubleshooting

| Message | Fix |
|---|---|
| `GitHub App private key not found` | Check `GITHUB_APP_PRIVATE_KEY_PATH` and that the file exists |
| `GitHub rejected the App credentials` | Wrong App ID, or the key belongs to another App |
| `the GitHub App is not installed on …` | Click **Connect GitHub** and include that repository |
| `invalid or expired connect request` | The link is valid for 15 minutes; click **Connect GitHub** again |
| `cannot access YOUR-USER/victim-service` | During install you didn't select that repo. Configure the installation on GitHub and add it |

## Simulating a teammate conflict on real GitHub

The "Simulate teammate push" button only works with the local provider, because AutoSRE never pushes to `main` on
a real repository. To demo the outer loop on GitHub, open `analytics/views.py` in the GitHub web editor while the PR is
open, change `LIMIT 50` to `LIMIT 100`, and commit to `main`. Within about 10 seconds AutoSRE notices the conflict and repairs it.
