export default function EmptyState({ databaseEmpty, lastRun, onReset }) {
  if (databaseEmpty) {
    const failed = lastRun?.status === "error";
    return (
      <div className="empty">
        <h2>Baza jest jeszcze pusta</h2>
        {failed ? (
          <>
            <p>Ostatnia próba pobrania danych z API BZP zakończyła się błędem:</p>
            <p className="empty__error mono">{lastRun.message || "brak szczegółów"}</p>
            <p>
              Otwórz na adresie backendu <span className="mono">/api/debug/bzp</span>,
              żeby zobaczyć pełną diagnostykę połączenia z API.
            </p>
          </>
        ) : (
          <>
            <p>
              Pierwsze pobieranie danych z Biuletynu Zamówień Publicznych trwa zwykle
              kilka minut. Strona odświeży się sama, gdy pojawią się wyniki.
            </p>
            <p className="empty__hint mono">
              Postęp: GET /api/stats · ręczne wywołanie: POST /api/scrape (opis w README)
            </p>
          </>
        )}
      </div>
    );
  }
  return (
    <div className="empty">
      <h2>Brak ogłoszeń dla tych filtrów</h2>
      <p>Zmień kryteria wyszukiwania albo wyłącz filtr „Tylko aktualne”.</p>
      <button className="btn btn--ghost" type="button" onClick={onReset}>
        Wyczyść filtry
      </button>
    </div>
  );
}
