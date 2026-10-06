import { useEffect, useRef, useState } from "react";
import type { CSSProperties, KeyboardEvent as ReactKeyboardEvent } from "react";
import { api } from "../api";
import type { Clue, VerifyResponse } from "../api";
import { clueSlots } from "./Board";

const key = (r: number, c: number) => `${r},${c}`;
const MAX_NUMBERS = 4;

type Entry = "numbers" | "solution";
type Mark = "wall" | "clue";

/** Elle bulmaca girme.
 *
 *  İki yol var, çünkü kitapta iki ayrı sayfa var:
 *
 *  **Sayılardan** — bulmaca sayfasına bakıyorsan. Hücreye rakamları yazarsın.
 *  **Çözümden**   — çözüm sayfasına bakıyorsan. Duvarı çizip ipucu hücrelerini
 *                   işaretlersin; sayıları motor hesaplar.
 */
export function Editor() {
  const [entry, setEntry] = useState<Entry>("numbers");
  const [rows, setRows] = useState(8);
  const [cols, setCols] = useState(8);

  const [clues, setClues] = useState<Record<string, number[]>>({});
  const [marks, setMarks] = useState<Record<string, Mark>>({});
  const [derived, setDerived] = useState<Record<string, number[]>>({});

  const [cursor, setCursor] = useState<[number, number]>([0, 0]);
  const [number, setNumber] = useState("");
  const [source, setSource] = useState("");
  const [result, setResult] = useState<VerifyResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(0);
  const painting = useRef<Mark | "clear" | null>(null);

  useEffect(() => {
    api
      .listHuman()
      .then((items) => setSaved(items.length))
      .catch(() => undefined);
  }, []);

  const reset = () => {
    setClues({});
    setMarks({});
    setDerived({});
    setResult(null);
    setCursor([0, 0]);
  };

  const touched = () => {
    setResult(null);
    setDerived({});
  };

  // ------------------------------------------------------------------ //
  // Sayılardan giriş
  // ------------------------------------------------------------------ //

  const writeClue = (r: number, c: number, values: number[]) => {
    setClues((current) => {
      const next = { ...current };
      if (values.length) next[key(r, c)] = values;
      else delete next[key(r, c)];
      return next;
    });
    touched();
  };

  // ------------------------------------------------------------------ //
  // Çözümden giriş
  // ------------------------------------------------------------------ //

  const setMark = (r: number, c: number, mark: Mark | null) => {
    setMarks((current) => {
      const next = { ...current };
      if (mark) next[key(r, c)] = mark;
      else delete next[key(r, c)];
      return next;
    });
    touched();
  };

  const toggle = (r: number, c: number, right: boolean): Mark | "clear" => {
    const current = marks[key(r, c)];
    if (right) {
      const target = current === "clue" ? null : "clue";
      setMark(r, c, target);
      return target ?? "clear";
    }
    const target = current === "wall" ? null : "wall";
    setMark(r, c, target);
    return target ?? "clear";
  };

  const extend = (r: number, c: number) => {
    if (painting.current === null) return;
    const target = painting.current === "clear" ? null : painting.current;
    if (marks[key(r, c)] !== (target ?? undefined)) setMark(r, c, target);
  };

  const gridRows = (): string[] =>
    Array.from({ length: rows }, (_, r) =>
      Array.from({ length: cols }, (_, c) => {
        const mark = marks[key(r, c)];
        return mark === "wall" ? "#" : mark === "clue" ? "o" : ".";
      }).join(""),
    );

  // ------------------------------------------------------------------ //

  const resize = (nextRows: number, nextCols: number) => {
    const keep = <T,>(source: Record<string, T>): Record<string, T> => {
      const next: Record<string, T> = {};
      for (const [cell, value] of Object.entries(source)) {
        const [r, c] = cell.split(",").map(Number);
        if (r < nextRows && c < nextCols) next[cell] = value;
      }
      return next;
    };
    setRows(nextRows);
    setCols(nextCols);
    setClues(keep);
    setMarks(keep);
    setDerived({});
    setResult(null);
    setCursor([0, 0]);
  };

  const onKeyDown = (event: ReactKeyboardEvent) => {
    const [r, c] = cursor;
    const moves: Record<string, [number, number]> = {
      ArrowUp: [r - 1, c],
      ArrowDown: [r + 1, c],
      ArrowLeft: [r, c - 1],
      ArrowRight: [r, c + 1],
    };

    if (moves[event.key]) {
      event.preventDefault();
      const [nr, nc] = moves[event.key];
      if (nr >= 0 && nc >= 0 && nr < rows && nc < cols) setCursor([nr, nc]);
      return;
    }

    if (entry === "numbers") {
      if (/^[0-8]$/.test(event.key)) {
        event.preventDefault();
        const current = clues[key(r, c)] ?? [];
        if (current.length < MAX_NUMBERS) writeClue(r, c, [...current, Number(event.key)]);
        return;
      }
      if (event.key === "Backspace") {
        event.preventDefault();
        writeClue(r, c, (clues[key(r, c)] ?? []).slice(0, -1));
        return;
      }
      if (event.key === "Delete" || event.key === " ") {
        event.preventDefault();
        writeClue(r, c, []);
      }
      return;
    }

    if (event.key === " " || event.key === "Enter") {
      event.preventDefault();
      toggle(r, c, false);
      return;
    }
    if (event.key.toLowerCase() === "o") {
      event.preventDefault();
      toggle(r, c, true);
      return;
    }
    if (event.key === "Backspace" || event.key === "Delete") {
      event.preventDefault();
      setMark(r, c, null);
    }
  };

  // ------------------------------------------------------------------ //

  const asClues = (): Clue[] =>
    Object.entries(clues).map(([cell, values]) => {
      const [r, c] = cell.split(",").map(Number);
      return { r, c, values };
    });

  const applyResponse = (response: VerifyResponse) => {
    setResult(response);
    if (entry === "solution" && response.clues) {
      const map: Record<string, number[]> = {};
      for (const clue of response.clues) map[key(clue.r, clue.c)] = clue.values;
      setDerived(map);
    }
  };

  const verify = async () => {
    setBusy(true);
    try {
      applyResponse(
        entry === "numbers"
          ? await api.verifyEntry(rows, cols, asClues())
          : await api.verifySolution(rows, cols, gridRows()),
      );
    } catch (error) {
      setResult({ ok: false, status: "hata", message: (error as Error).message, code: "" });
    } finally {
      setBusy(false);
    }
  };

  const save = async () => {
    setBusy(true);
    try {
      const response =
        entry === "numbers"
          ? await api.saveEntry(rows, cols, asClues(), number, source)
          : await api.saveSolution(rows, cols, gridRows(), number, source);
      applyResponse(response);
      if (response.saved) {
        setSaved(response.total ?? saved + 1);
        setClues({});
        setMarks({});
        setDerived({});
        setCursor([0, 0]);
        const next = Number(number);
        if (number.trim() !== "" && !Number.isNaN(next)) setNumber(String(next + 1));
      }
    } catch (error) {
      setResult({ ok: false, status: "hata", message: (error as Error).message, code: "" });
    } finally {
      setBusy(false);
    }
  };

  const filled =
    entry === "numbers" ? Object.keys(clues).length : Object.keys(marks).length;

  return (
    <main className="stage">
      <div className="stage__board">
        <div
          className="board"
          role="grid"
          aria-label="Bulmaca düzenleyici"
          tabIndex={0}
          onKeyDown={onKeyDown}
          onContextMenu={(event) => event.preventDefault()}
          onPointerUp={() => (painting.current = null)}
          onPointerLeave={() => (painting.current = null)}
          style={{ "--cols": cols, "--rows": rows } as CSSProperties}
        >
          {Array.from({ length: rows }, (_, r) =>
            Array.from({ length: cols }, (_, c) => {
              const cell = key(r, c);
              const mark = marks[cell];
              const values = entry === "numbers" ? clues[cell] : derived[cell];
              const classes = ["cell"];

              if (entry === "numbers") {
                if (values) classes.push("cell--clue");
              } else {
                if (mark === "wall") classes.push("cell--filled");
                if (mark === "clue") classes.push("cell--clue");
                if (mark === "wall" && marks[key(r, c + 1)] === "wall") classes.push("join-right");
                if (mark === "wall" && marks[key(r + 1, c)] === "wall") classes.push("join-down");
              }
              if (cursor[0] === r && cursor[1] === c) classes.push("cell--cursor");

              return (
                <div
                  key={cell}
                  className={classes.join(" ")}
                  role="gridcell"
                  onPointerDown={(event) => {
                    setCursor([r, c]);
                    if (entry === "solution") {
                      painting.current = toggle(r, c, event.button === 2);
                    }
                  }}
                  onPointerEnter={() => entry === "solution" && extend(r, c)}
                >
                  {values && (
                    <div className={`clue clue--${values.length}`}>
                      {values.map((value, index) => (
                        <span
                          key={index}
                          className={`clue__n clue__n--${clueSlots(values.length)[index]}`}
                        >
                          {value}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              );
            }),
          )}
        </div>

        <p className="muted">
          {entry === "numbers"
            ? "Hücreye tıkla ya da oklarla gez, rakamları yaz. Aynı hücreye birden çok rakam yazılabilir; geri tuşu son rakamı siler."
            : "Sol tık duvar örer (sürükleyerek de olur), sağ tık ipucu hücresini işaretler. Klavyede boşluk duvar, O ipucu hücresi."}
        </p>
      </div>

      <aside className="rail">
        <section className="rail__block">
          <h2>Giriş yolu</h2>
          <div className="bar__modes">
            <button
              className={entry === "numbers" ? "is-open" : ""}
              onClick={() => {
                setEntry("numbers");
                reset();
              }}
            >
              Sayılardan
            </button>
            <button
              className={entry === "solution" ? "is-open" : ""}
              onClick={() => {
                setEntry("solution");
                reset();
              }}
            >
              Çözümden
            </button>
          </div>
          <p className="muted">
            {entry === "numbers"
              ? "Bulmaca sayfasına bakıyorsan bu yol. Girdiğin sayılar doğrudan kullanılır."
              : "Çözüm sayfasına bakıyorsan bu yol. Sayıları motor duvardan hesaplar."}
          </p>
        </section>

        <section className="rail__block">
          <h2>Izgara</h2>
          <div className="sizes">
            <label>
              satır
              <input
                type="number"
                min={3}
                max={40}
                value={rows}
                onChange={(event) => resize(Number(event.target.value) || 3, cols)}
              />
            </label>
            <label>
              sütun
              <input
                type="number"
                min={3}
                max={40}
                value={cols}
                onChange={(event) => resize(rows, Number(event.target.value) || 3)}
              />
            </label>
          </div>
          <p className="muted">{filled} hücre işaretli.</p>
        </section>

        <section className="rail__block">
          <h2>Kaynak</h2>
          <div className="sizes">
            <label>
              no
              <input value={number} onChange={(event) => setNumber(event.target.value)} />
            </label>
          </div>
          <input
            placeholder="kitap / dergi adı"
            value={source}
            onChange={(event) => setSource(event.target.value)}
          />
          <p className="muted">Kaydedilen bulmaca sayısı: {saved}</p>
        </section>

        <section className="rail__block">
          <h2>Denetim</h2>
          <button className="wide" onClick={verify} disabled={busy || !filled}>
            Doğrula
          </button>
          <button className="wide" onClick={save} disabled={busy || !filled}>
            Kaydet
          </button>
          {result && <p className={result.ok ? "deduce" : "alarm"}>{result.message}</p>}
          {result?.code && <code className="codeline">{result.code}</code>}

          {entry === "numbers" ? (
            <p className="muted">
              Kayıt yalnızca tek çözümlü bulmacalarda yapılır. Tek bir rakam yanlış girildiyse
              bulmaca neredeyse her zaman çözümsüz ya da çok çözümlü çıkar; denetim bunu yakalar.
            </p>
          ) : (
            <p className="muted">
              Doğrulamadan sonra hesaplanan sayılar ızgarada görünür. Bu kipte denetim daha
              zayıftır: yanlış çizilen bir duvar da geçerli olabildiği için sayılar ona göre
              hesaplanır ve tutarlı görünür. Kitaptaki sayılarla karşılaştırmak son kontrol.
            </p>
          )}
        </section>

        <section className="rail__block">
          <h2>Temizle</h2>
          <button className="wide" onClick={reset} disabled={!filled}>
            Izgarayı boşalt
          </button>
        </section>
      </aside>
    </main>
  );
}
