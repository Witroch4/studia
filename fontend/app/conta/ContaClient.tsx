"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { authClient, useSession } from "@/lib/auth-client";
import BillingSection from "./BillingSection";
import { apiUrl } from "@/lib/api";
import { useAtualizarPerfil, useMeuPerfil, useRemoverAvatar, useSubirAvatar } from "./usePerfil";
import VisibilidadeCard from "./VisibilidadeCard";
import ResumoCard from "./ResumoCard";

type Notice = { kind: "ok" | "err"; msg: string } | null;

export default function ContaClient() {
  const { data: session, isPending } = useSession();
  const user = session?.user as
    | { name?: string; email?: string; role?: string }
    | undefined;
  const isAdmin = user?.role === "admin";
  const { data: perfil } = useMeuPerfil();

  return (
    <div className="px-6 py-8 md:px-10 max-w-3xl w-full mx-auto">
      <div className="flex items-center gap-2 text-sm text-fg-muted mb-6">
        <Link href="/" className="hover:text-fg">Home</Link>
        <span className="material-symbols-outlined text-[16px]">chevron_right</span>
        <span className="text-fg">Minha conta</span>
      </div>

      <div className="flex items-center gap-4 mb-8">
        <div className="h-14 w-14 rounded-full bg-gradient-to-tr from-primary to-secondary p-[2px]">
          {perfil?.avatar_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={apiUrl(perfil.avatar_url)}
              alt="Foto de perfil"
              className="rounded-full h-full w-full object-cover"
            />
          ) : (
            <div className="rounded-full h-full w-full bg-surface-dark flex items-center justify-center">
              <span className="text-lg font-bold text-fg-strong">
                {(user?.name || user?.email || "?").slice(0, 2).toUpperCase()}
              </span>
            </div>
          )}
        </div>
        <div>
          <h1 className="text-2xl font-bold text-fg-strong">{isPending ? "…" : user?.name || "Conta"}</h1>
          <p className="text-sm text-fg-faint">
            {user?.email}
            {perfil?.apelido && <span className="text-primary"> · @{perfil.apelido}</span>}
          </p>
        </div>
        {isAdmin && (
          <span className="ml-auto inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold uppercase tracking-wide text-secondary bg-secondary/10">
            <span className="material-symbols-outlined text-[14px]">shield_person</span> admin
          </span>
        )}
      </div>

      <div className="space-y-6">
        <BillingSection />
        <ProfileCard name={user?.name} email={user?.email} />
        <VisibilidadeCard />
        <ResumoCard />
        <PasswordCard />
        {isAdmin && <CreateUserCard />}
      </div>
    </div>
  );
}

function SectionCard({ title, icon, children }: { title: string; icon: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-border-dark bg-surface-dark p-6">
      <h2 className="flex items-center gap-2 text-base font-semibold text-fg-strong mb-4">
        <span className="material-symbols-outlined text-primary text-[20px]">{icon}</span>
        {title}
      </h2>
      {children}
    </section>
  );
}

function Field({ label, ...props }: { label: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="block">
      <span className="block text-[0.7rem] font-semibold uppercase tracking-wide text-fg-faint mb-1.5">{label}</span>
      <input
        {...props}
        className="w-full rounded-lg border border-border-dark bg-bg-dark py-2.5 px-3 text-sm text-fg-strong placeholder:text-fg-faint outline-none focus:border-primary focus:ring-1 focus:ring-primary disabled:opacity-50 transition-colors"
      />
    </label>
  );
}

function NoticeBox({ notice }: { notice: Notice }) {
  if (!notice) return null;
  const ok = notice.kind === "ok";
  return (
    <div className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm ${ok ? "border border-success/40 bg-success/10 text-success" : "border border-error/40 bg-error/10 text-error"}`}>
      <span className="material-symbols-outlined text-[18px]">{ok ? "check_circle" : "error"}</span>
      {notice.msg}
    </div>
  );
}

function PrimaryBtn({ loading, children }: { loading: boolean; children: React.ReactNode }) {
  return (
    <button
      type="submit"
      disabled={loading}
      className="inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white shadow-[0_8px_24px_rgba(6,182,212,0.30)] hover:bg-primary-600 disabled:opacity-50 transition-colors"
    >
      {loading && <span className="material-symbols-outlined text-[18px] animate-spin">progress_activity</span>}
      {children}
    </button>
  );
}

function ProfileCard({ name: initialName, email }: { name?: string; email?: string }) {
  const [name, setName] = useState(initialName || "");
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);
  const { data: perfil, isPending: perfilPending } = useMeuPerfil();
  const [apelido, setApelido] = useState<string | null>(null); // null = ainda não editado
  const atualizar = useAtualizarPerfil();
  const subirAvatar = useSubirAvatar();
  const removerAvatar = useRemoverAvatar();
  const fileRef = useRef<HTMLInputElement>(null);

  const apelidoAtual = apelido ?? perfil?.apelido ?? "";

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setNotice(null);
    const { error } = await authClient.updateUser({ name });
    let msgErro = error?.message;
    if (!msgErro && apelido !== null && apelido !== (perfil?.apelido ?? "")) {
      try {
        await atualizar.mutateAsync({ apelido });
      } catch (err) {
        msgErro = err instanceof Error ? err.message : "Erro ao salvar o apelido.";
      }
    }
    setLoading(false);
    setNotice(msgErro ? { kind: "err", msg: msgErro } : { kind: "ok", msg: "Perfil atualizado." });
  }

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setNotice(null);
    try {
      await subirAvatar.mutateAsync(file);
      setNotice({ kind: "ok", msg: "Foto atualizada." });
    } catch (err) {
      setNotice({ kind: "err", msg: err instanceof Error ? err.message : "Erro ao enviar a foto." });
    }
  }

  return (
    <SectionCard title="Perfil" icon="badge">
      <form onSubmit={save} className="space-y-4">
        <div className="flex items-center gap-4">
          <div className="h-16 w-16 rounded-full bg-bg-dark overflow-hidden flex items-center justify-center shrink-0">
            {perfil?.avatar_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={apiUrl(perfil.avatar_url)} alt="Foto de perfil" className="h-full w-full object-cover" />
            ) : (
              <span className="material-symbols-outlined text-fg-faint text-[32px]">person</span>
            )}
          </div>
          <div className="flex flex-col gap-1.5">
            <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={onFile} />
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              disabled={subirAvatar.isPending}
              className="text-sm text-primary hover:underline disabled:opacity-50 text-left"
            >
              {subirAvatar.isPending ? "Enviando…" : perfil?.avatar_url ? "Trocar foto" : "Inserir foto"}
            </button>
            {perfil?.avatar_url && (
              <button
                type="button"
                onClick={() => removerAvatar.mutate()}
                disabled={removerAvatar.isPending}
                className="text-sm text-fg-faint hover:text-error disabled:opacity-50 text-left"
              >
                Remover foto
              </button>
            )}
            <span className="text-xs text-fg-faint">png, jpg ou webp, até 5 MB</span>
          </div>
        </div>

        <Field label="Nome" value={name} onChange={(e) => setName(e.target.value)} placeholder="Seu nome" />
        <Field
          label="Apelido único (fórum)"
          value={apelidoAtual}
          onChange={(e) => setApelido(e.target.value.toLowerCase())}
          placeholder={perfilPending ? "carregando…" : "ex.: rochedo-16"}
          disabled={perfilPending}
        />
        <p className="text-xs text-fg-faint -mt-2">
          3 a 32 caracteres: letras minúsculas, números e hífens. Seu perfil público fica em /u/apelido.
        </p>
        <Field label="E-mail" value={email || ""} disabled />
        <NoticeBox notice={notice} />
        <PrimaryBtn loading={loading || atualizar.isPending}>Salvar perfil</PrimaryBtn>
      </form>
    </SectionCard>
  );
}

function PasswordCard() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setNotice(null);
    const { error } = await authClient.changePassword({
      currentPassword: current,
      newPassword: next,
      revokeOtherSessions: true,
    });
    setLoading(false);
    if (error) {
      setNotice({ kind: "err", msg: error.message || "Erro ao trocar senha." });
    } else {
      setNotice({ kind: "ok", msg: "Senha alterada." });
      setCurrent("");
      setNext("");
    }
  }

  return (
    <SectionCard title="Segurança" icon="lock">
      <form onSubmit={save} className="space-y-4">
        <Field label="Senha atual" type="password" value={current} onChange={(e) => setCurrent(e.target.value)} placeholder="••••••" />
        <Field label="Nova senha" type="password" value={next} onChange={(e) => setNext(e.target.value)} placeholder="••••••" />
        <NoticeBox notice={notice} />
        <PrimaryBtn loading={loading}>Trocar senha</PrimaryBtn>
      </form>
    </SectionCard>
  );
}

function CreateUserCard() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("user");
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setNotice(null);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { error } = await authClient.admin.createUser({ name, email, password, role: role as any });
    setLoading(false);
    if (error) {
      setNotice({ kind: "err", msg: error.message || "Erro ao criar usuário." });
    } else {
      setNotice({ kind: "ok", msg: `Usuário ${email} criado.` });
      setName("");
      setEmail("");
      setPassword("");
      setRole("user");
    }
  }

  return (
    <SectionCard title="Criar usuário (admin)" icon="group_add">
      <form onSubmit={create} className="space-y-4">
        <Field label="Nome" value={name} onChange={(e) => setName(e.target.value)} placeholder="Nome do usuário" required />
        <Field label="E-mail" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="usuario@email.com" required />
        <Field label="Senha" type="text" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="senha inicial" required />
        <label className="block">
          <span className="block text-[0.7rem] font-semibold uppercase tracking-wide text-fg-faint mb-1.5">Papel</span>
          <select
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className="w-full rounded-lg border border-border-dark bg-bg-dark py-2.5 px-3 text-sm text-fg-strong outline-none focus:border-primary focus:ring-1 focus:ring-primary"
          >
            <option value="user">user</option>
            <option value="professor">professor</option>
            <option value="admin">admin</option>
          </select>
        </label>
        <NoticeBox notice={notice} />
        <PrimaryBtn loading={loading}>Criar usuário</PrimaryBtn>
      </form>
      <Link href="/q/admin/usuarios" className="mt-3 block text-sm text-primary hover:underline">
        Gerenciar usuários e papéis →
      </Link>
    </SectionCard>
  );
}
