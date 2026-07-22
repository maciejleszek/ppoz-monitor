export default function Filters({
  qDraft,
  onQDraft,
  filters,
  regions,
  onChange,
  onReset,
  hasActive,
}) {
  return (
    <div className="filters" role="search">
      <input
        className="input filters__search"
        type="search"
        placeholder="Szukaj: SSP, hydranty, oddymianie, nazwa gminy…"
        value={qDraft}
        onChange={(e) => onQDraft(e.target.value)}
        aria-label="Szukaj w ogłoszeniach"
      />

      <select
        className="select"
        value={filters.region}
        onChange={(e) => onChange({ region: e.target.value })}
        aria-label="Województwo"
      >
        <option value="">Wszystkie województwa</option>
        {regions.map((r) => (
          <option key={r} value={r}>
            {r}
          </option>
        ))}
      </select>

      <select
        className="select"
        value={filters.source}
        onChange={(e) => onChange({ source: e.target.value })}
        aria-label="Źródło"
      >
        <option value="">Wszystkie źródła</option>
        <option value="bzp">BZP (krajowe)</option>
        <option value="bk">Baza Konkurencyjności (fundusze UE)</option>
        <option value="ted">TED (unijne)</option>
      </select>

      <select
        className="select"
        value={filters.sort}
        onChange={(e) => onChange({ sort: e.target.value })}
        aria-label="Sortowanie"
      >
        <option value="newest">Najnowsze</option>
        <option value="deadline">Najbliższy termin ofert</option>
        <option value="oldest">Najstarsze</option>
      </select>

      <label className="toggle">
        <input
          type="checkbox"
          checked={filters.activeOnly}
          onChange={(e) => onChange({ activeOnly: e.target.checked })}
        />
        <span>Tylko aktualne</span>
      </label>

      {hasActive && (
        <button className="btn btn--ghost" type="button" onClick={onReset}>
          Wyczyść filtry
        </button>
      )}
    </div>
  );
}
