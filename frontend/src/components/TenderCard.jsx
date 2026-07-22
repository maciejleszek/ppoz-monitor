import {
  SOURCE_LABELS,
  daysLeft,
  daysLeftLabel,
  deadlineStatus,
  fmtDate,
  fmtDateTime,
} from "../utils";

export default function TenderCard({ tender, onOpen }) {
  const left = daysLeft(tender.submission_deadline);
  const status = deadlineStatus(tender.submission_deadline);
  const keywords = tender.matched_keywords || [];

  return (
    <article className={`card card--${status}`}>
      <div className="card__main">
        <div className="card__meta">
          <span className="badge">{SOURCE_LABELS[tender.source] || tender.source}</span>
          <span className="mono card__date">{fmtDate(tender.publication_date)}</span>
          {tender.region && <span className="card__region">{tender.region}</span>}
          {tender.order_type && <span className="card__ordertype">{tender.order_type}</span>}
        </div>

        <h3 className="card__title">
          <button type="button" onClick={() => onOpen(tender)}>
            {tender.title}
          </button>
        </h3>

        {tender.buyer_name && (
          <p className="card__buyer">
            {tender.buyer_name}
            {tender.city ? ` · ${tender.city}` : ""}
          </p>
        )}

        {keywords.length > 0 && (
          <div className="chips">
            {keywords.slice(0, 5).map((k) => (
              <span key={k} className="chip">
                {k}
              </span>
            ))}
            {keywords.length > 5 && (
              <span className="chip chip--more">+{keywords.length - 5}</span>
            )}
          </div>
        )}
      </div>

      <div className="card__aside">
        <span className="card__dl-label">termin ofert</span>
        <span className="card__dl-date mono">
          {tender.submission_deadline ? fmtDateTime(tender.submission_deadline) : "—"}
        </span>
        {left !== null && <span className={`dl dl--${status}`}>{daysLeftLabel(left)}</span>}

        <div className="card__actions">
          {tender.url && (
            <a
              className="btn btn--primary"
              href={tender.url}
              target="_blank"
              rel="noopener noreferrer"
            >
              Ogłoszenie ↗
            </a>
          )}
          <button className="btn btn--ghost" type="button" onClick={() => onOpen(tender)}>
            Szczegóły
          </button>
        </div>
      </div>
    </article>
  );
}
