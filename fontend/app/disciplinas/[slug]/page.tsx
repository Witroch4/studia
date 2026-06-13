"use client";

import Link from "next/link";
import { useState, useEffect, use } from "react";
import PdfUploader from "../../components/PdfUploader";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type AulaData = {
  id: number;
  numero: number;
  titulo: string;
  status: string;
  modelo_usado: string | null;
  erro_msg: string | null;
  created_at: string | null;
};

type DisciplinaDetail = {
  id: number;
  slug: string;
  nome: string;
  descricao: string | null;
  icon: string;
  icon_color: string;
  aulas: AulaData[];
};

const STATUS_STYLES: Record<string, { bg: string; text: string; icon: string; label: string }> = {
  PENDENTE: { bg: "bg-amber-500/15", text: "text-amber-400", icon: "schedule", label: "Pendente" },
  PROCESSANDO: { bg: "bg-primary/15", text: "text-primary", icon: "sync", label: "Processando" },
  CONCLUIDO: { bg: "bg-accent-success/15", text: "text-accent-success", icon: "check_circle", label: "Concluído" },
  ERRO: { bg: "bg-accent-error/15", text: "text-accent-error", icon: "error", label: "Erro" },
};

export default function DisciplinaPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  const [data, setData] = useState<DisciplinaDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [showUpload, setShowUpload] = useState(false);
  const [uploading, setUploading] = useState(false);

  const fetchData = () => {
    fetch(`${API_URL}/api/disciplinas/${slug}`)
      .then((r) => r.json())
      .then((d) => setData(d))
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchData();
    // Poll para atualizar status de aulas processando
    const interval = setInterval(() => {
      fetchData();
    }, 10000);
    return () => clearInterval(interval);
  }, [slug]);

  const handleUpload = async (file: File, modelo: string) => {
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("modelo", modelo);

      const res = await fetch(`${API_URL}/api/disciplinas/${slug}/aulas`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json();
        alert(err.detail || "Erro no upload");
        return;
      }

      setShowUpload(false);
      fetchData();
    } catch (err) {
      console.error(err);
      alert("Erro na conexão");
    } finally {
      setUploading(false);
    }
  };

  if (loading) {
    return (
      <main className="w-full px-4 md:px-8 py-8">
        <div className="animate-pulse space-y-6">
          <div className="h-8 w-64 bg-surface-2 rounded" />
          <div className="h-4 w-48 bg-surface rounded" />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="bg-surface-dark rounded-xl border border-border-dark p-6 h-32" />
            ))}
          </div>
        </div>
      </main>
    );
  }

  if (!data) {
    return (
      <main className="w-full px-4 md:px-8 py-8">
        <p className="text-fg-muted">Disciplina não encontrada.</p>
      </main>
    );
  }

  return (
    <>
      <header className="hidden md:flex sticky top-0 z-30 bg-bg-dark/80 backdrop-blur-md border-b border-border-dark px-8 py-4 justify-between items-center">
        <div className="flex items-center gap-3">
          <Link href="/disciplinas" className="text-fg-muted hover:text-fg-strong transition-colors">
            <span className="material-symbols-outlined">arrow_back</span>
          </Link>
          <h1 className="text-2xl font-bold text-fg-strong">{data.nome}</h1>
        </div>
      </header>

      <main className="w-full px-4 md:px-8 py-8 overflow-y-auto h-full">
        {/* Info */}
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-8 gap-4">
          <div>
            <h2 className="text-3xl font-bold text-fg-strong mb-1">{data.nome}</h2>
            {data.descricao && <p className="text-sm text-fg-muted">{data.descricao}</p>}
            <p className="text-xs text-fg-faint mt-2">
              {data.aulas.length} {data.aulas.length === 1 ? "aula" : "aulas"} cadastradas
            </p>
          </div>
          <button
            onClick={() => setShowUpload(!showUpload)}
            className="flex items-center gap-2 px-5 py-2.5 bg-primary hover:bg-cyan-600 text-white rounded-lg shadow-lg shadow-cyan-500/20 transition-all font-medium whitespace-nowrap"
          >
            <span className="material-symbols-outlined text-sm">{showUpload ? "close" : "add"}</span>
            {showUpload ? "Fechar" : "Adicionar Aula"}
          </button>
        </div>

        {/* Upload form */}
        {showUpload && (
          <div className="mb-8 max-w-lg">
            <PdfUploader onUpload={handleUpload} uploading={uploading} />
          </div>
        )}

        {/* Lista de aulas */}
        <div className="space-y-4 pb-8">
          {data.aulas.length === 0 && !showUpload && (
            <div className="bg-surface-dark border border-dashed border-border rounded-xl p-12 text-center">
              <span className="material-symbols-outlined text-5xl text-fg-faint mb-4 block">description</span>
              <h3 className="text-lg font-bold text-fg-strong mb-2">Nenhuma aula ainda</h3>
              <p className="text-sm text-fg-muted mb-6">Faça upload de um PDF para criar sua primeira aula.</p>
              <button
                onClick={() => setShowUpload(true)}
                className="inline-flex items-center gap-2 px-5 py-2.5 bg-primary hover:bg-cyan-600 text-white rounded-lg font-medium transition-all"
              >
                <span className="material-symbols-outlined text-sm">upload_file</span>
                Upload PDF
              </button>
            </div>
          )}

          {data.aulas.map((aula) => {
            const st = STATUS_STYLES[aula.status] || STATUS_STYLES.PENDENTE;
            const isReady = aula.status === "CONCLUIDO";
            const isProcessing = aula.status === "PROCESSANDO";

            return (
              <div
                key={aula.id}
                className="bg-surface-dark border border-border-dark rounded-xl hover:border-primary/30 transition-all"
              >
                <div className="flex items-center gap-4 p-5">
                  {/* Número da aula */}
                  <div className="flex-shrink-0 h-14 w-14 rounded-xl bg-primary/10 flex flex-col items-center justify-center">
                    <span className="text-[10px] text-primary/70 uppercase font-bold">Aula</span>
                    <span className="text-xl font-bold text-primary">{String(aula.numero).padStart(2, "0")}</span>
                  </div>

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <h4 className="text-base font-semibold text-fg-strong truncate">{aula.titulo}</h4>
                    <div className="flex items-center gap-3 mt-1">
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${st.bg} ${st.text}`}>
                        <span className={`material-symbols-outlined text-[14px] ${isProcessing ? "animate-spin" : ""}`}>
                          {st.icon}
                        </span>
                        {st.label}
                      </span>
                      {aula.modelo_usado && (
                        <span className="text-xs text-fg-faint flex items-center gap-1">
                          <span className="material-symbols-outlined text-[12px]">smart_toy</span>
                          {aula.modelo_usado}
                        </span>
                      )}
                    </div>
                    {aula.erro_msg && (
                      <p className="text-xs text-accent-error mt-1 truncate">{aula.erro_msg}</p>
                    )}
                  </div>

                  {/* Ações */}
                  <div className="flex items-center gap-2 flex-shrink-0">
                    {isReady ? (
                      <Link
                        href={`/disciplinas/${slug}/aulas/${aula.id}`}
                        className="flex items-center gap-2 px-4 py-2 bg-primary hover:bg-cyan-600 text-white rounded-lg text-sm font-medium transition-colors"
                      >
                        <span className="material-symbols-outlined text-[18px]">menu_book</span>
                        Estudar
                      </Link>
                    ) : isProcessing ? (
                      <div className="flex items-center gap-2 px-4 py-2 bg-surface-2 text-primary rounded-lg text-sm font-medium">
                        <div className="h-3 w-3 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
                        Processando...
                      </div>
                    ) : (
                      <span className="text-xs text-fg-faint">Aguardando</span>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </main>
    </>
  );
}
