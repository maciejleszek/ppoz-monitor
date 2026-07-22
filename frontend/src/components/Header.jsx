import { fmtDateTime } from "../utils";

export default function Header({ stats }) {
  const lastRun = stats?.last_run;
  return (
    <header className="header">
      <div className="container header__inner">
        <div className="brand">
          <span className="brand__mark" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="22" height="22">
              <path
                fill="currentColor"
                d="M12 3.5c-2.4 3.2 1.6 4.4-.8 7.2-1 1.1-2.4-.4-2-1.6-2.3 1.2-2.8 3.3-2.8 4.5 0 3.3 2.5 5.9 5.6 5.9s5.6-2.6 5.6-5.9c0-2.6-2.1-4.2-3.4-6.4-.9-1.5-1.4-2.6-2.2-3.7z"
              />
            </svg>
          </span>
          <div>
            <h1 className="brand__name">PPOŻ Monitor</h1>
            <p className="brand__tag">Przetargi publiczne · ochrona przeciwpożarowa</p>
          </div>
        </div>

        <div className="header__status">
          {lastRun ? (
            <>
              <span
                className={`led ${lastRun.status === "ok" ? "led--ok" : lastRun.status === "running" ? "led--busy" : "led--alert"}`}
                aria-hidden="true"
              />
              <span className="header__status-text mono">
                {lastRun.status === "running"
                  ? "pobieranie w toku…"
                  : `aktualizacja ${fmtDateTime(lastRun.finished_at || lastRun.started_at)}`}
              </span>
            </>
          ) : (
            <span className="header__status-text mono">system gotowy</span>
          )}
        </div>
      </div>
    </header>
  );
}
