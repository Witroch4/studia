import { StatCard, ProgressBar } from "./components/ds";

const disciplinas = [
  { nome: "Cálculo Numérico", tempo: "10h06min", acertos: 210, erros: 53, total: 263, pct: 80 },
  { nome: "Mecânica dos Fluídos", tempo: "17h18min", acertos: 59, erros: 16, total: 75, pct: 79 },
  { nome: "Resistência dos Materiais", tempo: "3h45min", acertos: 98, erros: 24, total: 122, pct: 80 },
  { nome: "Termodinâmica", tempo: "6h25min", acertos: 22, erros: 7, total: 29, pct: 76 },
  { nome: "Física III (Eletromagnetismo)", tempo: "6h50min", acertos: 4, erros: 3, total: 7, pct: 57 },
  { nome: "Algoritmos e Estrutura de Dados", tempo: "10h42min", acertos: 41, erros: 8, total: 49, pct: 84 },
];

function pctColor(pct: number) {
  if (pct >= 80) return "bg-accent-success/20 text-accent-success";
  if (pct >= 70) return "bg-secondary/20 text-secondary";
  return "bg-accent-error/20 text-accent-error";
}

export default function Home() {
  return (
    <>
      <header className="hidden md:flex sticky top-0 z-40 bg-bg-dark/80 backdrop-blur-md border-b border-border-dark px-8 py-4 justify-between items-center">
        <h1 className="text-2xl font-bold text-white">Dashboard</h1>
        <div className="flex items-center gap-4">
          <button className="p-2 rounded-full hover:bg-gray-800 text-gray-300 relative">
            <span className="material-symbols-outlined">notifications</span>
            <span className="absolute top-2 right-2 h-2 w-2 rounded-full bg-secondary animate-pulse" />
          </button>
        </div>
      </header>

      <main className="w-full px-4 md:px-8 py-8 overflow-y-auto h-full">
        {/* Title + Actions */}
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-8 gap-4">
          <div className="text-3xl font-bold text-white">Visão Geral</div>
          <div className="flex gap-3">
            <button className="flex items-center gap-2 px-4 py-2 bg-primary hover:bg-cyan-600 text-white rounded-lg shadow-lg shadow-cyan-500/30 transition-all font-medium">
              <span className="material-symbols-outlined text-sm">add</span>
              Registrar Estudo
            </button>
            <button className="flex items-center gap-2 px-4 py-2 bg-surface-dark border border-gray-600 hover:bg-gray-700 text-gray-200 rounded-lg transition-all font-medium">
              <span className="material-symbols-outlined text-sm">language</span>
              Meu Plano
              <span className="material-symbols-outlined text-sm">expand_more</span>
            </button>
          </div>
        </div>

        {/* Stat Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          <StatCard
            title="Total de Horas"
            icon="schedule"
            iconColor="primary"
            progress={65}
          >
            <span className="text-4xl font-bold text-white">
              55h<span className="text-2xl text-gray-400">08min</span>
            </span>
          </StatCard>

          <StatCard
            title="Precisão Técnica"
            icon="precision_manufacturing"
            iconColor="secondary"
            progress={80}
          >
            <div className="flex items-end justify-between w-full">
              <div>
                <span className="text-sm text-accent-success font-medium">434 Acertos</span>
                <div className="text-xs text-accent-error font-medium">111 Erros</div>
              </div>
              <span className="text-4xl font-bold text-white">80%</span>
            </div>
          </StatCard>

          <StatCard
            title="Cronograma do Semestre"
            icon="calendar_month"
            iconColor="success"
            progress={19}
          >
            <div className="flex items-end justify-between w-full">
              <div>
                <span className="text-sm text-accent-success font-medium">17 Tópicos Concluídos</span>
                <div className="text-xs text-amber-500 font-medium">72 Pendentes</div>
              </div>
              <span className="text-4xl font-bold text-white">19%</span>
            </div>
          </StatCard>

          <div className="bg-gradient-to-br from-gray-800 to-black p-6 rounded-xl shadow-sm border border-gray-700 flex items-center justify-center text-center relative overflow-hidden">
            <div className="absolute inset-0 bg-secondary/10" />
            <p className="text-gray-200 italic font-light z-10 text-sm">
              &ldquo;A engenharia é a arte de modelar materiais que não entendemos completamente, em formas que não podemos analisar com precisão, para suportar forças que não podemos avaliar adequadamente.&rdquo;
            </p>
          </div>
        </div>

        {/* Streak */}
        <div className="bg-surface-dark p-6 rounded-xl shadow-sm border border-border-dark mb-8">
          <div className="flex justify-between items-end mb-4">
            <div>
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Constância nos Estudos</h3>
              <p className="text-gray-200 mt-1">
                Você está há <span className="font-bold text-primary">8 dias</span> sem falhar no código!
              </p>
            </div>
          </div>
          <div className="flex gap-2 overflow-x-auto pb-2">
            {Array.from({ length: 20 }).map((_, i) => {
              const isSuccess = [2, 7, 8, 10, 11, 12, 14, 15, 16, 17, 18, 19].includes(i);
              return (
                <div
                  key={i}
                  className={`flex-shrink-0 w-8 h-8 rounded flex items-center justify-center ${
                    i < 2
                      ? "bg-gray-700"
                      : isSuccess
                      ? "bg-primary/20 border border-primary/50 text-primary"
                      : "bg-accent-error/10 border border-accent-error/30 text-accent-error"
                  }`}
                >
                  {i >= 2 && (
                    <span className="material-symbols-outlined text-sm">
                      {isSuccess ? "terminal" : "error_outline"}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Bottom Grid: Disciplinas Table + Side Cards */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Disciplinas Table */}
          <div className="lg:col-span-2 bg-surface-dark p-6 rounded-xl shadow-sm border border-border-dark">
            <div className="flex justify-between items-center mb-6">
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Painel de Disciplinas</h3>
              <button className="text-gray-400 hover:text-primary transition-colors">
                <span className="material-symbols-outlined">filter_list</span>
              </button>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead className="text-xs text-gray-400 uppercase bg-gray-800/50">
                  <tr>
                    <th className="px-4 py-3 rounded-l-lg">Disciplinas</th>
                    <th className="px-4 py-3 text-center">Tempo</th>
                    <th className="px-4 py-3 text-center text-accent-success">
                      <span className="material-symbols-outlined text-base align-middle">check</span>
                    </th>
                    <th className="px-4 py-3 text-center text-accent-error">
                      <span className="material-symbols-outlined text-base align-middle">close</span>
                    </th>
                    <th className="px-4 py-3 text-center">
                      <span className="material-symbols-outlined text-base align-middle">edit_note</span>
                    </th>
                    <th className="px-4 py-3 text-center rounded-r-lg">%</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800">
                  {disciplinas.map((d, i) => (
                    <tr key={d.nome} className={`hover:bg-gray-800/30 transition-colors ${i % 2 === 1 ? "bg-gray-800/10" : ""}`}>
                      <td className="px-4 py-4 font-medium text-primary">{d.nome}</td>
                      <td className="px-4 py-4 text-center text-gray-300">{d.tempo}</td>
                      <td className="px-4 py-4 text-center text-accent-success font-medium">{d.acertos}</td>
                      <td className="px-4 py-4 text-center text-accent-error font-medium">{d.erros}</td>
                      <td className="px-4 py-4 text-center text-gray-300">{d.total}</td>
                      <td className="px-4 py-4 text-center">
                        <span className={`${pctColor(d.pct)} px-2 py-1 rounded text-xs font-bold`}>{d.pct}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Side Cards */}
          <div className="flex flex-col gap-8">
            {/* Weekly Goals */}
            <div className="bg-surface-dark p-6 rounded-xl shadow-sm border border-border-dark">
              <div className="flex justify-between items-start mb-6">
                <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Metas de Estudo Semanal</h3>
                <span className="material-symbols-outlined text-gray-400 text-sm cursor-pointer hover:text-primary">edit</span>
              </div>
              <div className="space-y-6">
                <GoalProgress label="Horas de Estudo" current="3h35min" target="35h00min" pct={10.3} color="bg-primary" badgeColor="bg-primary/80" />
                <GoalProgress label="Questões" current="122" target="250" pct={48.8} color="bg-secondary" badgeColor="bg-secondary/80" />
              </div>
            </div>

            {/* Skills Radar Placeholder */}
            <div className="bg-surface-dark p-6 rounded-xl shadow-sm border border-border-dark flex-grow">
              <div className="flex justify-between items-center mb-2">
                <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Radar de Habilidades</h3>
              </div>
              <div className="relative h-64 w-full flex items-center justify-center">
                <div className="text-gray-500 text-sm flex flex-col items-center gap-2">
                  <span className="material-symbols-outlined text-4xl text-primary/30">radar</span>
                  <span>Gráfico de habilidades</span>
                </div>
              </div>
              <div className="flex justify-end gap-2 mt-4">
                <button className="px-3 py-1 bg-primary text-white text-xs font-bold rounded shadow">TEORIA</button>
                <button className="px-3 py-1 bg-gray-700 text-gray-300 text-xs font-bold rounded border border-gray-600">PRÁTICA</button>
              </div>
            </div>
          </div>
        </div>
      </main>
    </>
  );
}

function GoalProgress({
  label,
  current,
  target,
  pct,
  color,
  badgeColor,
}: {
  label: string;
  current: string;
  target: string;
  pct: number;
  color: string;
  badgeColor: string;
}) {
  return (
    <div>
      <div className="flex justify-between text-sm mb-2">
        <span className="text-gray-400">{current} / {target}</span>
        <span className="font-medium text-gray-200">{label}</span>
      </div>
      <div className="relative pt-1">
        <div className="flex mb-2 items-center justify-between">
          <span className={`text-xs font-semibold inline-block py-1 px-2 uppercase rounded-full text-white ${badgeColor}`}>
            {pct}%
          </span>
        </div>
        <div className="mb-4">
          <ProgressBar value={pct} color={color === "bg-secondary" ? "secondary" : "primary"} height={8} />
        </div>
      </div>
    </div>
  );
}
