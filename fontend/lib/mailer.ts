import "server-only";
import nodemailer, { type Transporter } from "nodemailer";

/**
 * Mailer transacional — studIA.
 *
 * Usa a conta Zoho compartilhada da WitDev (`suporte@witdev.com.br`). As creds
 * vêm das mesmas vars `SMTP_*` do stack compartilhado (build.sh as copia do
 * `stack-portainer.env` para /opt/studia/.env). Se nenhum SMTP estiver
 * configurado (caso típico de dev), caímos no modo "console": o link de
 * verificação/reset é logado no terminal em vez de falhar — assim o cadastro
 * com verificação obrigatória continua testável localmente sem servidor SMTP.
 */

const host = process.env.SMTP_ADDRESS || process.env.SMTP_HOST;
const port = Number(process.env.SMTP_PORT || 587);
const user = process.env.SMTP_USERNAME;
const pass = process.env.SMTP_PASSWORD;
// 465 = TLS implícito; 587 = STARTTLS (secure=false + requireTLS).
const secure = port === 465;

const FROM =
  process.env.MAILER_SENDER_EMAIL ||
  (user ? `studIA <${user}>` : "studIA <suporte@witdev.com.br>");

const smtpConfigured = !!(host && user && pass);

let transporter: Transporter | null = null;
function getTransport(): Transporter | null {
  if (!smtpConfigured) return null;
  if (!transporter) {
    transporter = nodemailer.createTransport({
      host,
      port,
      secure,
      requireTLS: !secure,
      auth: { user, pass },
    });
  }
  return transporter;
}

type SendArgs = { to: string; subject: string; html: string; text?: string };

export async function sendEmail({ to, subject, html, text }: SendArgs): Promise<void> {
  const tx = getTransport();
  if (!tx) {
    // Modo dev sem SMTP: loga em vez de enviar (não quebra o fluxo).
    console.warn(
      `[mailer] SMTP não configurado — e-mail NÃO enviado.\n` +
        `  to:      ${to}\n  subject: ${subject}\n  text:    ${text ?? "(html only)"}`
    );
    return;
  }
  await tx.sendMail({ from: FROM, to, subject, html, text });
}

/** Layout escuro simples, alinhado à marca studIA (cyan #06b6d4). */
function shell(title: string, bodyHtml: string, cta: { url: string; label: string }): string {
  return `
  <div style="background:#121212;padding:32px 16px;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:480px;margin:0 auto;">
      <tr><td style="padding-bottom:24px;text-align:center;">
        <span style="font-size:24px;font-weight:800;color:#fff;">stud<span style="color:#06b6d4;">IA</span></span>
      </td></tr>
      <tr><td style="background:#1e1e1e;border:1px solid #2a2a2a;border-radius:16px;padding:28px;">
        <h1 style="margin:0 0 12px;font-size:18px;color:#fff;">${title}</h1>
        <div style="font-size:14px;line-height:1.6;color:#b5b5b5;">${bodyHtml}</div>
        <div style="text-align:center;margin:28px 0 8px;">
          <a href="${cta.url}" style="display:inline-block;background:#06b6d4;color:#fff;text-decoration:none;font-weight:600;font-size:14px;padding:12px 28px;border-radius:10px;">${cta.label}</a>
        </div>
        <p style="font-size:12px;color:#777;margin:16px 0 0;">Se o botão não funcionar, copie e cole este link no navegador:</p>
        <p style="font-size:12px;color:#06b6d4;word-break:break-all;margin:4px 0 0;">${cta.url}</p>
      </td></tr>
      <tr><td style="padding-top:20px;text-align:center;font-size:11px;color:#666;">
        Você recebeu este e-mail porque criou (ou tentou recuperar) uma conta no studIA.
      </td></tr>
    </table>
  </div>`;
}

export async function sendVerificationEmail(to: string, url: string): Promise<void> {
  await sendEmail({
    to,
    subject: "Confirme seu e-mail — studIA",
    text: `Confirme seu e-mail para ativar sua conta no studIA:\n${url}`,
    html: shell(
      "Confirme seu e-mail",
      "Falta só um passo para ativar sua conta e começar a estudar. Clique no botão abaixo para confirmar este endereço de e-mail.",
      { url, label: "Confirmar e-mail" }
    ),
  });
}

export async function sendResetPasswordEmail(to: string, url: string): Promise<void> {
  await sendEmail({
    to,
    subject: "Redefinir sua senha — studIA",
    text: `Você pediu para redefinir sua senha no studIA. Acesse:\n${url}\n\nSe não foi você, ignore este e-mail.`,
    html: shell(
      "Redefinir senha",
      "Recebemos um pedido para redefinir a senha da sua conta. Clique no botão abaixo para escolher uma nova senha. Se não foi você, pode ignorar este e-mail com segurança.",
      { url, label: "Redefinir senha" }
    ),
  });
}
