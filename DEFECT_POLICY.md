# Defect Tracking & Resolution Policy ("Every Change is a Bug")

## 1. Core Principle
Any modification to codebase, documentation, presentations, migration tooling, or infrastructure is classified as a defect/task that must be tracked in CLEBUGGER from inception to validation.

## 2. Standard Defect Lifecycle
```
[User Request / GitHub Issue / Discovery]
                  │
                  ▼
         1. Create Defect (OPEN / IN_PROGRESS)
            `python bug.py add JRFK "<title>" --build "<build>" --comp "<component>"`
                  │
                  ▼
         2. Implement Changes & Fixes
                  │
                  ▼
         3. Test & Validate
            (Playwright visual verification, unit/e2e tests)
                  │
                  ▼
         4. Resolve Defect (RESOLVED)
            `python bug.py resolve <ID> "<resolution details>"`
                  │
                  ▼
         5. Recalculate Codebase Metrics
            `python bug.py scan JRFK`
```

## 3. GitHub Issue Synchronization
- **Daily Ingestion**: GitHub issues on `jbirdlebough1/JRFKTools` are automatically checked daily at 09:00 AM via Windows Task Scheduler (`CLEBugger_Daily_GitHub_Sync`) and the Antigravity recurring scheduler.
- **On-Demand Sync**: Execute `python bug.py sync-github JRFK` or run `sync_github_daily.bat`.
- **Automatic De-duplication**: Issues are assigned `[GH#<number>]` prefixes and will not be duplicated on repeated sync runs.
- **Closing Sync**: When an issue is closed upstream on GitHub, subsequent sync runs automatically transition the CLEBugger defect to `RESOLVED`.
