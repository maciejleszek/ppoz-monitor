// Pasek statystyk stylizowany na wyświetlacz centrali sygnalizacji pożarowej.

function Cell({ label, value, tone = "", led = "" }) {
  return (
    <div className="lcd__cell">
      <span className="lcd__label">
        {led && <span className={`led ${led}`} aria-hidden="true" />}
        {label}
      </span>
      <span className={`lcd__value ${tone}`}>{value ?? "—"}</span>
    </div>
  );
}

export default function Lcd({ stats }) {
  return (
    <div className="lcd" role="status" aria-label="Statystyki bazy ogłoszeń">
      <div className="container lcd__inner">
        <Cell label="w bazie" value={stats?.total} />
        <Cell label="nowe 24h" value={stats?.new_24h} led="led--ok" />
        <Cell label="nowe 7 dni" value={stats?.new_7d} />
        <Cell
          label="termin ≤ 7 dni"
          value={stats?.closing_7d}
          tone="lcd__value--alert"
          led="led--alert"
        />
      </div>
    </div>
  );
}
