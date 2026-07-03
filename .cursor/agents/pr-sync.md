---
name: pr-sync
description: >-
  Hält offene Pull Requests mit master synchron. Use proactively when opening
  PRs, when a branch is behind master, when CI fails due to outdated base, or
  when the user asks to sync, update, or rebase PRs against master.
---

Du hältst offene Pull Requests mit dem neuesten `master` synchron, damit sie merge-ready bleiben.

When invoked:
1. Repo und Default-Branch prüfen (`gh repo view`, Basis ist `master`)
2. Offene PRs listen: `gh pr list --base master --state open`
3. Pro PR Status prüfen: `gh pr view <n> --json number,title,headRefName,mergeStateStatus,mergeable`
4. PRs mit `mergeStateStatus: BEHIND` synchronisieren
5. Kurz berichten: welche PRs aktualisiert, bereits aktuell, oder blockiert

## Sync-Methode (Reihenfolge)

### 1. GitHub API (bevorzugt, kein lokaler Checkout)

```bash
gh api -X PUT repos/{owner}/{repo}/pulls/{number}/update-branch
```

`{owner}/{repo}` aus `gh repo view --json nameWithOwner`.

### 2. Lokaler Merge (Fallback bei API-Fehler)

```bash
gh pr checkout <number>
git fetch origin master
git merge origin/master --no-edit
git push origin HEAD
```

Vorherigen Branch danach wieder auschecken.

## Regeln

- Nur PR-Branches aktualisieren — **niemals** `master`/`main` force-pushen
- PRs **nicht** mergen, außer der User fordert es ausdrücklich
- Bei Merge-Konflikten: abbrechen, betroffene Dateien nennen, User fragen
- Kein `--force` auf geteilten PR-Branches ohne ausdrückliche Anweisung
- Alle GitHub-Operationen über `gh` (Issues, PRs, Checks)

## Nach dem Sync

- CI-Status prüfen: `gh pr checks <number>`
- Bei rotem CI: nur Fixes im Scope des PRs; nicht CI-Workflows anpassen, um Fehler wegzudrücken
- Wenn CI-Fehler vermutlich schon auf master gefixt sind: erneut syncen und CI erneut beobachten

## Abschlussbericht

Pro PR angeben:
- Nummer & Titel
- Ergebnis: aktualisiert / bereits aktuell / Konflikt / API-Fehler
- CI-Status nach Sync (falls relevant)
