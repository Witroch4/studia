"use client";

import { useState } from "react";
import Link from "next/link";
import { authClient, useSession } from "@/lib/auth-client";
import BillingSection from "./BillingSection";

type Notice = { kind: "ok" | "err"; msg: string } | null;

export default function ContaClient() {
  const { data: session, isPending } = useSession();
  const user = session?.user as
    | { name?: string; email?: string; role?: string }
    | undefined;
  const isAdmin = user?.role === "admin";

  return (
    <div className="px-6 py-8 md:px-10 max-w-3xl w-full mx-auto">
      <div className="flex items-center gap-2 text-sm text-fg-muted mb-6">
        <Link href="/" className="hover:text-fg">Home</Link>
        <span className="material-symbols-outlined text-[16px]">chevron_right</span>
        <span className="text-fg">Minha conta</span>
      </div>

      <div className="flex items-center gap-4 mb-8">
        <div className="h-14 w-14 rounded-full bg-gradient-to-tr from-primary to-secondary p-[2px]">
          <div className="rounded-full h-full w-full bg-surface-dark flex items-center justify-center">
            <span className="text-lg font-bold text-fg-strong">
              {(user?.name || user?.email || "?").slice(0, 2).toUpperCase()}
            </span>
          </div>
        </div>
        <div>
          <h1 className="text-2xl font-bold text-fg-strong">{isPending ? "…" : user?.name || "Conta"}</h1>
          <p className="text-sm text-fg-faint">{user?.email}</p>
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

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setNotice(null);
    const { error } = await authClient.updateUser({ name });
    setLoading(false);
    setNotice(error ? { kind: "err", msg: error.message || "Erro ao salvar." } : { kind: "ok", msg: "Perfil atualizado." });
  }

  return (
    <SectionCard title="Perfil" icon="badge">
      <form onSubmit={save} className="space-y-4">
        <Field label="Nome" value={name} onChange={(e) => setName(e.target.value)} placeholder="Seu nome" />
        <Field label="E-mail" value={email || ""} disabled />
        <NoticeBox notice={notice} />
        <PrimaryBtn loading={loading}>Salvar perfil</PrimaryBtn>
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
    const { error } = await authClient.admin.createUser({ name, email, password, role: role as "user" | "admin" });
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
            <option value="admin">admin</option>
          </select>
        </label>
        <NoticeBox notice={notice} />
        <PrimaryBtn loading={loading}>Criar usuário</PrimaryBtn>
      </form>
    </SectionCard>
  );
}
