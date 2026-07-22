import { useEffect, useState } from "react";
import { getRegions, getStats, getTenders } from "./api";
import Header from "./components/Header.jsx";
import Lcd from "./components/Lcd.jsx";
import Filters from "./components/Filters.jsx";
import TenderCard from "./components/TenderCard.jsx";
import TenderModal from "./components/TenderModal.jsx";
import Pagination from "./components/Pagination.jsx";
import EmptyState from "./components/EmptyState.jsx";

const DEFAULT_FILTERS = { q: "", region: "", source: "", sort: "newest", activeOnly: true };

export default function App() {
  const [qDraft, setQDraft] = useState("");
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [page, setPage] = useState(1);
  const [data, setData] = useState({ items: [], total: 0, pages: 1 });
  const [stats, setStats] = useState(null);
  const [regions, setRegions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null);

  // Debounce pola wyszukiwania.
  useEffect(() => {
    const t = setTimeout(() => {
      setFilters((f) => (f.q === qDraft ? f : { ...f, q: qDraft }));
      setPage(1);
    }, 350);
    return () => clearTimeout(t);
  }, [qDraft]);

  // Statystyki i lista województw — raz przy starcie.
  useEffect(() => {
    getStats().then(setStats).catch(() => {});
    getRegions().then(setRegions).catch(() => {});
  }, []);

  // Lista ogłoszeń — przy każdej zmianie filtrów lub strony.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    getTenders({ ...filters, page })
      .then((d) => !cancelled && setData(d))
      .catch(() => {
        if (!cancelled)
          setError("Nie udało się pobrać danych. Sprawdź, czy backend działa, i odśwież stronę.");
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [filters, page]);

  const updateFilters = (patch) => {
    setFilters((f) => ({ ...f, ...patch }));
    setPage(1);
  };

  const resetFilters = () => {
    setQDraft("");
    setFilters(DEFAULT_FILTERS);
    setPage(1);
  };

  const hasActiveFilters =
    filters.q || filters.region || filters.source || !filters.activeOnly || filters.sort !== "newest";

  return (
    <div className="page">
      <Header stats={stats} />
      <Lcd stats={stats} />

      <main className="container">
        <Filters
          qDraft={qDraft}
          onQDraft={setQDraft}
          filters={filters}
          regions={regions}
          onChange={updateFilters}
          onReset={resetFilters}
          hasActive={hasActiveFilters}
        />

        <div className="results-bar">
          <span className="results-bar__count">
            {loading ? "Ładowanie…" : `Wyników: ${data.total}`}
          </span>
        </div>

        {error && <div className="alert">{error}</div>}

        {!loading && !error && data.items.length === 0 && (
          <EmptyState databaseEmpty={(stats?.total ?? 0) === 0} onReset={resetFilters} />
        )}

        <section className="cards" aria-busy={loading}>
          {data.items.map((t) => (
            <TenderCard key={t.id} tender={t} onOpen={setSelected} />
          ))}
        </section>

        {data.pages > 1 && (
          <Pagination page={page} pages={data.pages} onPage={setPage} disabled={loading} />
        )}
      </main>

      <footer className="footer">
        <p>
          Źródła danych: Biuletyn Zamówień Publicznych (oficjalne API platformy
          e‑Zamówienia, UZP){stats?.sources?.ted ? " oraz TED — Tenders Electronic Daily" : ""}.
        </p>
        <p>
          Serwis ma charakter informacyjny — przed złożeniem oferty zawsze zweryfikuj treść
          ogłoszenia u źródła.
        </p>
      </footer>

      {selected && <TenderModal tender={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
