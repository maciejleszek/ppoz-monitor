export default function EmptyState({ databaseEmpty, onReset }) {
  if (databaseEmpty) {
    return (
      <div className="empty">
        <h2>Baza jest jeszcze pusta</h2>
        <p>
          Pierwsze pobieranie danych z Biuletynu Zamówień Publicznych uruchamia się
          automatycznie po starcie serwera i trwa kilka minut. Odśwież stronę za chwilę.
        </p>
        <p className="empty__hint mono">
          Pobieranie możesz też wywołać ręcznie: POST /api/scrape (opis w README).
        </p>
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
