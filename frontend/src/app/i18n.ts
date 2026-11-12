// Dicionário de rótulos da interface (EN/PT). Conteúdo dos achados vem do motor, em inglês.
export type Lang = "en" | "pt";

const dict = {
  dashboard: ["Dashboard", "Painel"],
  training: ["Training Diagnostics", "Diagnóstico de Treino"],
  dataset: ["Dataset Quality", "Qualidade do Dataset"],
  tokenizer: ["Tokenizer Efficiency", "Eficiência do Tokenizer"],
  generation: ["Generation Behavior", "Comportamento de Geração"],
  compare: ["Experiment Comparison", "Comparação de Experimentos"],
  investigate: ["Root-Cause Investigation", "Investigação de Causa Raiz"],
  lab: ["Model Lab (live)", "Laboratório de Modelos"],
  monitor: ["Production Monitor", "Monitor de Produção"],
  reports: ["Reports", "Relatórios"],
  projects: ["Projects & Experiments", "Projetos e Experimentos"],
  settings: ["Settings", "Configurações"],
  project: ["Project", "Projeto"],
  experiment: ["Experiment", "Experimento"],
  status: ["Status", "Status"],
  runAudit: ["Run audit", "Executar auditoria"],
  run: ["Run", "Executar"],
  cancel: ["Cancel", "Cancelar"],
  noExperiment: ["No experiment selected", "Nenhum experimento selecionado"],
  noReport: ["No analysis yet for this experiment", "Nenhuma análise para este experimento"],
  loadDemo: ["Load demo lab", "Carregar demo"],
  ask: ["Ask about the selected experiment…", "Pergunte sobre o experimento selecionado…"],
  findings: ["Findings", "Achados"],
  hypotheses: ["Hypotheses", "Hipóteses"],
  experiments: ["Recommended experiments", "Experimentos recomendados"],
  evidence: ["Evidence", "Evidências"],
  limitations: ["Limitations", "Limitações"],
  export: ["Export", "Exportar"],
  backendOnline: ["Backend online", "Backend online"],
  backendOffline: ["Backend offline", "Backend offline"],
  demoBanner: ["DEMO MODE — results computed by the real engine on synthetic data", "MODO DEMO — resultados do motor real sobre dados sintéticos"],
} as const;

export type I18nKey = keyof typeof dict;
export const translate = (lang: Lang, key: I18nKey): string => dict[key][lang === "pt" ? 1 : 0];
