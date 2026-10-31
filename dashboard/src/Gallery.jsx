import { useEffect, useRef, useState } from "react";
import { Icon } from "./Illustrations";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "";
const TYPES = ["image/jpeg", "image/png", "image/webp", "image/gif"];

export default function Gallery() {
  const [photos, setPhotos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [progress, setProgress] = useState(null);
  const [selected, setSelected] = useState(null);
  const input = useRef(null);
  const dialog = useRef(null);
  const uploading = useRef(false);

  async function load() {
    const response = await fetch(`${API_BASE}/api/gallery`, { cache: "no-store" });
    if (!response.ok) throw new Error("Chưa tải được ảnh. Mình thử lại nhé.");
    const images = await response.json();
    setPhotos(images);
  }

  useEffect(() => {
    let active = true;
    async function refresh() {
      try {
        const response = await fetch(`${API_BASE}/api/gallery`, { cache: "no-store" });
        if (!response.ok) throw new Error();
        const images = await response.json();
        if (active) setPhotos(images);
      } catch { if (active) setError("Chưa tải được ảnh. Kiểm tra kết nối rồi thử lại nhé."); }
      finally { if (active) setLoading(false); }
    }
    refresh();
    const timer = setInterval(refresh, 15000);
    return () => { active = false; clearInterval(timer); };
  }, []);

  useEffect(() => {
    if (selected && !dialog.current.open) dialog.current.showModal();
    if (!selected && dialog.current.open) dialog.current.close();
  }, [selected]);

  async function upload(files) {
    if (!files.length || uploading.current) return;
    uploading.current = true;
    setError(""); setNotice("");
    let added = 0;
    const failed = [];
    try {
      for (const [index, file] of Array.from(files).entries()) {
        setProgress({ current: index + 1, total: files.length });
        if (!TYPES.includes(file.type) || file.size > 10 * 1024 * 1024) {
          failed.push(`${file.name}: chọn ảnh JPG, PNG, WebP hoặc GIF, tối đa 10 MB.`);
          continue;
        }
        try {
          const body = new FormData();
          body.append("file", file);
          const response = await fetch(`${API_BASE}/api/gallery`, { method: "POST", body });
          const result = await response.json();
          if (!response.ok || !result.ok) throw new Error();
          added += 1;
        } catch { failed.push(`${file.name}: chưa tải lên được, thử lại nhé.`); }
      }
      if (added) {
        setNotice(`Đã lưu ${added} khoảnh khắc của đôi mình.`);
        try { await load(); } catch { failed.push("Ảnh đã lưu nhưng chưa cập nhật được danh sách. Bấm tải lại nhé."); }
      }
      setError(failed.join("\n"));
    } finally {
      uploading.current = false; setProgress(null);
      if (input.current) input.current.value = "";
    }
  }

  function move(direction) {
    const index = photos.findIndex((photo) => photo.name === selected?.name);
    if (photos.length) setSelected(photos[(index + direction + photos.length) % photos.length]);
  }

  return <section id="memories" className="card memories-card" aria-label="Góc kỷ niệm">
    <div className="card-heading"><div><p className="eyebrow">Những ngày có nhau</p><h2>Góc kỷ niệm <span className="photo-count">{photos.length} ảnh</span></h2><p className="subtitle">Giữ lại những khoảnh khắc khiến mình mỉm cười.</p></div><span className="heart-mark"><Icon name="image" /></span></div>
    <div className="memory-upload" onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); upload(event.dataTransfer.files); }}>
      <div><strong>Thêm một chút kỷ niệm</strong><p>Kéo ảnh vào đây hoặc chọn từ thiết bị · Tối đa 10 MB mỗi ảnh</p></div>
      <input ref={input} type="file" accept={TYPES.join(",")} multiple hidden onChange={(event) => upload(event.target.files)} disabled={!!progress} />
      <button className="button primary" disabled={!!progress} onClick={() => input.current.click()}>{progress ? `Đang lưu ${progress.current}/${progress.total}…` : "+ Thêm ảnh"}</button>
    </div>
    {notice && <p className="notice success" role="status">{notice}</p>}
    {error && <div className="notice error" role="alert"><p className="gallery-error">{error}</p><button className="button secondary" onClick={async () => { setError(""); setLoading(true); try { await load(); } catch (err) { setError(err.message); } finally { setLoading(false); } }}>Tải lại ảnh</button></div>}
    {loading ? <p role="status" className="subtitle">Đang mở album của đôi mình…</p> : photos.length === 0 ? <div className="memory-empty"><Icon name="image" width="42" height="42" /><h3>Những điều đẹp nhất bắt đầu từ đây</h3><p>Một buổi hẹn, một chuyến đi, hay chỉ là nụ cười của người thương.</p></div> : <div className="memory-grid">{photos.map((photo, index) => <button className="memory-photo" key={photo.name} onClick={() => setSelected(photo)} aria-label={`Mở kỷ niệm ${index + 1}`}><img src={`${API_BASE}${photo.url}`} alt={`Khoảnh khắc của đôi mình ${index + 1}`} loading="lazy" /><span>{photo.updated_at ? new Date(photo.updated_at * 1000).toLocaleDateString("vi-VN") : "Kỷ niệm của đôi mình"}</span></button>)}</div>}
    <dialog ref={dialog} className="memory-dialog" aria-label="Xem ảnh kỷ niệm" onClose={() => setSelected(null)} onClick={(event) => { if (event.target === dialog.current) setSelected(null); }} onKeyDown={(event) => { if (event.key === "ArrowLeft") { event.preventDefault(); move(-1); } if (event.key === "ArrowRight") { event.preventDefault(); move(1); } }}>
      {selected && <div className="memory-viewer"><div className="viewer-toolbar"><span>Kỷ niệm {photos.findIndex((photo) => photo.name === selected.name) + 1} / {photos.length}</span><button className="button secondary" onClick={() => setSelected(null)} autoFocus>Đóng ×</button></div><img src={`${API_BASE}${selected.url}`} alt="Ảnh kỷ niệm của đôi mình" /><div className="viewer-toolbar"><button className="button secondary" disabled={photos.length < 2} onClick={() => move(-1)}>← Ảnh trước</button><button className="button secondary" disabled={photos.length < 2} onClick={() => move(1)}>Ảnh sau →</button></div></div>}
    </dialog>
  </section>;
}
