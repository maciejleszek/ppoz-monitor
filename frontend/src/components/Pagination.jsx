export default function Pagination({ page, pages, onPage, disabled }) {
  return (
    <nav className="pagination" aria-label="Paginacja wyników">
      <button
        className="btn btn--ghost"
        type="button"
        disabled={disabled || page <= 1}
        onClick={() => onPage(page - 1)}
      >
        ← Poprzednia
      </button>
      <span className="pagination__info mono">
        {page} / {pages}
      </span>
      <button
        className="btn btn--ghost"
        type="button"
        disabled={disabled || page >= pages}
        onClick={() => onPage(page + 1)}
      >
        Następna →
      </button>
    </nav>
  );
}
