import { useCallback, useEffect, useRef, useState } from "react";
import { Icon } from "./Illustrations";
import { locales, translate } from "./translations";

const TYPES = ["image/jpeg", "image/png", "image/webp", "image/gif"];
const PAGE_SIZE = 9;

function Photo({ photo, index, apiBase, t, onOpen, full = false }) {
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  const [original, setOriginal] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const src = `${apiBase}${full || original ? photo.url : photo.thumbnail_url || photo.url}`;
  const image = <img key={`${src}:${attempt}`} src={src} alt={t("memoryAlt")}
    loading={full || index < 3 ? "eager" : "lazy"} decoding="async"
    onLoad={() => setLoaded(true)} onError={() => {
      if (!full && !original && photo.thumbnail_url) setOriginal(true);
      else setFailed(true);
    }} />;

  if (full) return <div className={`album-full-photo ${loaded ? "is-loaded" : ""}`}>
    {!loaded && !failed && <span className="album-image-placeholder" aria-hidden="true"><Icon name="image" /></span>}
    {!failed && image}
    {failed && <div className="album-image-error" role="status"><Icon name="image" /><p>{t("photoFailed")}</p><button className="button secondary" onClick={() => { setFailed(false); setLoaded(false); setAttempt((value) => value + 1); }}>{t("retry")}</button></div>}
  </div>;

  return <button type="button" className={`album-tile ${loaded ? "is-loaded" : ""} ${failed ? "is-failed" : ""}`}
    onClick={onOpen} aria-label={t("openMemory", { number: index + 1 })}>
    <span className="album-image-placeholder" aria-hidden="true"><Icon name="image" /></span>
    {!failed && image}
    {failed && <span className="album-tile-error">{t("photoFailed")}<small>{t("openOriginal")}</small></span>}
    <span className="album-tile-caption"><span>{index === 0 ? t("featuredMemory") : t("littleMemory", { number: String(index + 1).padStart(2, "0") })}</span><Icon name="expand" width="17" height="17" /></span>
  </button>;
}

export default function AnniversaryGallery({ apiBase, language }) {
  const t = (key, values) => translate(language, key, values);
  const [photos, setPhotos] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [failures, setFailures] = useState([]);
  const [added, setAdded] = useState(0);
  const [progress, setProgress] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [visible, setVisible] = useState(PAGE_SIZE);
  const [selectedName, setSelectedName] = useState(null);
  const input = useRef(null);
  const dialog = useRef(null);
  const uploading = useRef(false);
  const requestId = useRef(0);

  const refresh = useCallback(async (signal) => {
    const id = ++requestId.current;
    try {
      const response = await fetch(`${apiBase}/api/gallery`, { cache: "no-store", signal });
      if (!response.ok) throw new Error();
      const next = await response.json();
      if (!Array.isArray(next)) throw new Error();
      if (id === requestId.current) { setPhotos(next); setLoadError(false); }
    } catch (error) {
      if (error.name !== "AbortError" && id === requestId.current) setLoadError(true);
    } finally {
      if (!signal?.aborted && id === requestId.current) setLoading(false);
    }
  }, [apiBase]);

  useEffect(() => {
    const controller = new AbortController();
    refresh(controller.signal);
    const timer = setInterval(() => {
      if (!document.hidden && !uploading.current) refresh(controller.signal);
    }, 30000);
    return () => { controller.abort(); clearInterval(timer); };
  }, [refresh]);

  const selectedIndex = photos?.findIndex((photo) => photo.name === selectedName) ?? -1;
  const selected = photos?.[selectedIndex];
  useEffect(() => {
    const element = dialog.current;
    if (!selected) { if (element.open) element.close(); return; }
    if (!element.open) element.showModal();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = overflow; };
  }, [selectedName, !!selected]);

  function move(direction) {
    if (photos?.length > 1) setSelectedName(photos[(selectedIndex + direction + photos.length) % photos.length].name);
  }

  async function upload(files) {
    const list = Array.from(files || []);
    if (!list.length || uploading.current) return;
    uploading.current = true;
    ++requestId.current;
    setFailures([]); setAdded(0); setDragging(false);
    const failed = [];
    let saved = 0;
    try {
      for (const [index, file] of list.entries()) {
        setProgress({ current: index + 1, total: list.length });
        if (!TYPES.includes(file.type) || file.size > 10 * 1024 * 1024) {
          failed.push({ name: file.name, key: "invalidPhoto" });
          continue;
        }
        try {
          const body = new FormData();
          body.append("file", file);
          const response = await fetch(`${apiBase}/api/gallery`, { method: "POST", body });
          const result = await response.json();
          if (!response.ok || !result.ok || !result.image) throw new Error();
          setPhotos((current) => [result.image, ...(current || []).filter((photo) => photo.name !== result.image.name)]);
          setAdded(++saved);
        } catch { failed.push({ name: file.name, key: "importFailed" }); }
      }
      setFailures(failed);
      if (saved || photos === null) await refresh();
    } finally {
      uploading.current = false;
      setProgress(null); setLoading(false);
      if (input.current) input.current.value = "";
    }
  }

  const count = photos?.length || 0;
  return <section id="gallery" className={`card gallery-card album ${dragging ? "is-dragging" : ""}`} aria-labelledby="album-title"
    onDragOver={(event) => { event.preventDefault(); if (event.dataTransfer.types.includes("Files")) setDragging(true); }}
    onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setDragging(false); }}
    onDrop={(event) => { event.preventDefault(); setDragging(false); upload(event.dataTransfer.files); }}>
    <div className="card-heading album-heading">
      <div><p className="eyebrow">{t("moments")}</p><h2 id="album-title">{t("gallery")}</h2><p className="subtitle">{t("galleryTagline")}</p></div>
      <button type="button" className="button secondary" onClick={() => input.current.click()} disabled={!!progress}><Icon name="plus" width="16" height="16" />{t("addPhotosShort")}</button>
      <input ref={input} type="file" accept={TYPES.join(",")} multiple hidden onChange={(event) => upload(event.target.files)} disabled={!!progress} />
    </div>

    {dragging && <div className="album-drop-overlay"><Icon name="image" width="36" height="36" /><strong>{t("dropPhotos")}</strong></div>}
    {progress && <div className="album-upload-progress" role="status"><div><span>{t("savingPhotos", progress)}</span><span>{progress.current}/{progress.total}</span></div><progress value={progress.current - 1} max={progress.total} aria-label={t("savingPhotos", progress)} /></div>}
    {added > 0 && !progress && <p className="notice success" role="status">{t(added === 1 ? "memoryAdded" : "memoriesAdded", { count: added })}</p>}
    {failures.length > 0 && <div className="notice error" role="alert">{failures.map((failure, index) => <p key={index}>{t(failure.key, failure)}</p>)}</div>}
    {loadError && <div className="album-load-error" role="alert"><span>{t("galleryFailed")}</span><button type="button" className="button secondary" disabled={loading} onClick={() => { setLoading(true); refresh(); }}>{t("retry")}</button></div>}

    <div aria-busy={loading && photos === null}>
      {photos === null && loading ? <><p className="album-status" role="status">{t("galleryLoading")}</p><div className="album-grid" aria-hidden="true">{Array.from({ length: PAGE_SIZE }, (_, index) => <div key={index} className="album-tile album-skeleton"><span className="album-image-placeholder"><Icon name="image" /></span></div>)}</div></>
        : count > 0 ? <div className="album-grid">{photos.slice(0, visible).map((photo, index) => <Photo key={`${photo.name}:${photo.thumbnail_url || photo.url}`} photo={photo} index={index} apiBase={apiBase} t={t} onOpen={() => setSelectedName(photo.name)} />)}</div>
          : !loadError && <div className="gallery-empty album-empty"><span><Icon name="image" width="28" height="28" /></span><strong>{t("galleryEmpty")}</strong><p>{t("galleryHint")}</p><button type="button" className="button secondary" onClick={() => input.current.click()} disabled={!!progress}>{t("firstPhoto")}</button></div>}
    </div>
    <div className="album-footer"><span><Icon name="heart" width="14" height="14" />{count > 0 ? t("photoCount", { count }) : t("galleryFootnote")}</span>{count > visible ? <button type="button" className="button secondary" onClick={() => setVisible((current) => current + PAGE_SIZE)}>{t("moreMemories")}<Icon name="chevronDown" width="15" height="15" /></button> : <small>{t("uploadHint")}</small>}</div>

    <dialog ref={dialog} className="album-dialog" aria-label={t("memoryViewer")} onClose={() => setSelectedName(null)}
      onClick={(event) => { if (event.target === dialog.current) setSelectedName(null); }}
      onKeyDown={(event) => { if (event.key === "ArrowLeft") { event.preventDefault(); move(-1); } if (event.key === "ArrowRight") { event.preventDefault(); move(1); } }}>
      {selected && <div className="album-viewer">
        <div className="album-viewer-heading"><div><p className="eyebrow">{t("moments")}</p><span>{t("memoryPosition", { current: selectedIndex + 1, total: count })}</span></div><button type="button" className="album-icon-button" aria-label={t("closeViewer")} onClick={() => setSelectedName(null)} autoFocus><Icon name="close" /></button></div>
        <Photo key={selected.name} photo={selected} index={selectedIndex} apiBase={apiBase} t={t} full />
        <div className="album-viewer-footer"><button type="button" className="album-icon-button" aria-label={t("previousPhoto")} onClick={() => move(-1)} disabled={count < 2}><Icon name="chevronLeft" /></button><div><span>{selected.updated_at ? new Date(selected.updated_at * 1000).toLocaleDateString(locales[language], { dateStyle: "long" }) : t("featuredMemory")}</span><a href={`${apiBase}${selected.url}`} target="_blank" rel="noreferrer">{t("openFullImage")}</a></div><button type="button" className="album-icon-button" aria-label={t("nextPhoto")} onClick={() => move(1)} disabled={count < 2}><Icon name="chevronRight" /></button></div>
      </div>}
    </dialog>
  </section>;
}
