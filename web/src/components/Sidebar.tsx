import { useState } from "react";
import type { Difficulty, HintResponse, Puzzle, PuzzleSummary, ValidateResponse } from "../api";

interface Props {
  library: PuzzleSummary[];
  puzzle: Puzzle | null;
  validation: ValidateResponse | null;
  hint: HintResponse | null;
  difficulty: Difficulty | null;
  live: boolean;
  notice: string | null;
  moveCount: number;
  onOpen: (id: string) => void;
  onCode: (code: string) => void;
  onToggleLive: () => void;
  onDownloadLog: () => void;
}

export function Sidebar({
  library,
  puzzle,
  validation,
  hint,
  difficulty,
  live,
  notice,
  moveCount,
  onOpen,
  onCode,
  onToggleLive,
  onDownloadLog,
}: Props) {
  const [code, setCode] = useState("");

  const issues = validation?.issues ?? [];

  return (
    <aside className="rail">
      <section className="rail__block">
        <h2>Bulmacalar</h2>
        <ul className="library">
          {library.map((item) => (
            <li key={item.id}>
              <button
                className={puzzle?.id === item.id ? "library__item is-open" : "library__item"}
                onClick={() => onOpen(item.id)}
              >
                <span>{String(item.meta.baslik ?? item.id)}</span>
                <span className="library__size">
                  {item.rows}×{item.cols} · {item.clueCount} ipucu
                </span>
              </button>
            </li>
          ))}
        </ul>
        {!library.length && <p className="muted">Kütüphane boş.</p>}
      </section>

      <section className="rail__block">
        <h2>Kendi bulmacan</h2>
        <p className="muted">
          Kısa kodu yapıştır: nokta boş hücre, rakam ipucu, çok sayılı ipucu parantez içinde.
        </p>
        <textarea
          className="code"
          rows={3}
          spellCheck={false}
          value={code}
          placeholder="6x6/....../.3..(11)./....../....../..0.../......"
          onChange={(event) => setCode(event.target.value)}
        />
        <button className="wide" onClick={() => code.trim() && onCode(code.trim())}>
          Bu bulmacayı aç
        </button>
      </section>

      <section className="rail__block">
        <h2>Zorluk</h2>
        {difficulty ? (
          <>
            <p className="level">
              {difficulty.label}
              {!difficulty.unique && " · birden çok çözüm"}
            </p>
            <p className="muted">
              {difficulty.logicOnly
                ? `${difficulty.deductions} hücre kesin çıkarımla yerleşiyor, varsayım gerekmiyor.`
                : `Saf mantık yetmiyor; çözüm ${difficulty.guesses} varsayım gerektiriyor.`}
            </p>
            <ul className="techniques">
              {Object.entries(difficulty.techniques).map(([name, count]) => (
                <li key={name}>
                  <span>{name}</span>
                  <span className="library__size">{count} hücre</span>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="muted">Ölçülüyor…</p>
        )}
      </section>

      <section className="rail__block">
        <h2>Durum</h2>
        <label className="toggle">
          <input type="checkbox" checked={live} onChange={onToggleLive} />
          <span>Hata yaptığım anda uyar</span>
        </label>

        {notice && <p className="alarm">{notice}</p>}

        {hint && <p className={hint.found ? "deduce" : "muted"}>{hint.reason}</p>}

        {issues.length > 0 ? (
          <ul className="issues">
            {issues.map((issue, index) => (
              <li key={index}>{issue.message}</li>
            ))}
          </ul>
        ) : (
          <p className="muted">
            {validation
              ? "Şu ana kadar kural ihlali yok."
              : "Hücrelere tıkla: sol tık duvar örer, sağ tık kesin boş işaretler."}
          </p>
        )}
      </section>

      <section className="rail__block">
        <h2>Çözüm kaydı</h2>
        <p className="muted">
          Bu oturumda {moveCount} hamle yapıldı. Kayıt, zorluk ölçmek için hamle zamanlarını
          içerir.
        </p>
        <button className="wide" onClick={onDownloadLog} disabled={!moveCount}>
          Kaydı indir
        </button>
        {puzzle && <code className="codeline">{puzzle.code}</code>}
      </section>
    </aside>
  );
}
