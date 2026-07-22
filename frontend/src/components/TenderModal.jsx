import { useEffect } from "react";
import { SOURCE_LABELS, daysLeft, daysLeftLabel, fmtDateTime } from "../utils";

export default function TenderModal({ tender, onClose }) {
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [onClose]);

  const left = daysLeft(tender.submission_deadline);

  return (
    <div className="modal" role="dialog" aria-modal="true" aria-label="Szczegóły ogłoszenia">
      <div className="modal__backdrop" onClick={onClose} />
      <div className="modal__panel">
        <button className="modal__close" type="button" onClick={onClose} aria-label="Zamknij">
          ✕
        </button>

        <div className="card__meta">
          <span className="badge">{SOURCE_LABELS[tender.source] || tender.source}</span>
          {tender.external_id && <span className="mono">{tender.external_id}</span>}
        </div>

        <h2 className="modal__title">{tender.title}</h2>

        <dl className="modal__grid">
          <div>
            <dt>Zamawiający</dt>
            <dd>{tender.buyer_name || "—"}</dd>
          </div>
          <div>
            <dt>Lokalizacja</dt>
            <dd>
              {[tender.city, tender.region].filter(Boolean).join(", ") || "—"}
            </dd>
          </div>
          <div>
            <dt>Rodzaj zamówienia</dt>
            <dd>{tender.order_type || "—"}</dd>
          </div>
          <div>
            <dt>Publikacja</dt>
            <dd className="mono">{fmtDateTime(tender.publication_date)}</dd>
          </div>
          <div>
            <dt>Termin składania ofert</dt>
            <dd className="mono">
              {fmtDateTime(tender.submission_deadline)}
              {left !== null && ` (${daysLeftLabel(left)})`}
            </dd>
          </div>
          <div>
            <dt>Kody CPV</dt>
            <dd className="mono">{(tender.cpv_codes || []).join(", ") || "—"}</dd>
          </div>
        </dl>

        {(tender.matched_keywords || []).length > 0 && (
          <div className="chips">
            {tender.matched_keywords.map((k) => (
              <span key={k} className="chip">
                {k}
              </span>
            ))}
          </div>
        )}

        {tender.description && <p className="modal__desc">{tender.description}</p>}

        <div className="modal__actions">
          {tender.url && (
            <a
              className="btn btn--primary"
              href={tender.url}
              target="_blank"
              rel="noopener noreferrer"
            >
              Otwórz ogłoszenie ↗
            </a>
          )}
          {tender.tender_url && (
            <a
              className="btn btn--ghost"
              href={tender.tender_url}
              target="_blank"
              rel="noopener noreferrer"
            >
              Strona postępowania ↗
            </a>
          )}
        </div>
      </div>
    </div>
  );
}
