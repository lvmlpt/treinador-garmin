"""
Garmin Connect Sync — Treinador
================================
Busca dados de saúde, atividade, sono e composição corporal do Garmin Connect
e salva como JSON na pasta do projeto para o Claude ler automaticamente.

INSTALAÇÃO (rode uma vez no terminal):
    pip install garminconnect curl_cffi

CONFIGURAÇÃO:
    Defina as variáveis GARMIN_EMAIL e GARMIN_PASSWORD abaixo,
    ou crie variáveis de ambiente com esses nomes.

EXECUÇÃO:
    python garmin_sync.py

AGENDAMENTO AUTOMÁTICO (Windows — opcional):
    Abra o Agendador de Tarefas > Criar Tarefa Básica
    Trigger: Diariamente às 07:00
    Ação: python "E:\\Documents\\Claude\\Projects\\Treinador\\garmin_sync.py"
"""

import json
import os
from datetime import date, timedelta
from pathlib import Path

# ── Configuração ──────────────────────────────────────────────────────────────
GARMIN_EMAIL    = os.getenv("GARMIN_EMAIL", "lvmaia@gmail.com")
GARMIN_PASSWORD = os.getenv("GARMIN_PASSWORD", "Lv@150282")
TOKEN_STORE     = str(Path.home() / ".garminconnect")
OUTPUT_DIR      = Path(__file__).parent  # mesma pasta do script
OUTPUT_FILE     = OUTPUT_DIR / "garmin_dados_atuais.json"
DIAS_HISTORICO  = 30  # quantos dias de histórico buscar

# ── Importação ────────────────────────────────────────────────────────────────
try:
    from garminconnect import Garmin
except ImportError:
    print("ERRO: biblioteca não instalada.")
    print("Execute: pip install garminconnect curl_cffi")
    raise SystemExit(1)

# ── Autenticação ──────────────────────────────────────────────────────────────
def fazer_login() -> Garmin:
    client = Garmin(
        email=GARMIN_EMAIL,
        password=GARMIN_PASSWORD,
        prompt_mfa=lambda: input("Código MFA (deixe vazio se não usar): ").strip() or None,
    )
    client.login(TOKEN_STORE)
    return client

# ── Coleta de dados ───────────────────────────────────────────────────────────
def coletar_dados(client: Garmin) -> dict:
    hoje = date.today()
    ontem = hoje - timedelta(days=1)
    inicio = hoje - timedelta(days=DIAS_HISTORICO)

    dados = {
        "sincronizado_em": hoje.isoformat(),
        "periodo": {
            "inicio": inicio.isoformat(),
            "fim": hoje.isoformat(),
        },
    }

    def safe(label, fn, *args, **kwargs):
        try:
            result = fn(*args, **kwargs)
            dados[label] = result
            print(f"  ✓ {label}")
        except Exception as e:
            dados[label] = None
            print(f"  ✗ {label}: {e}")

    print("\n👤 Perfil...")
    safe("perfil",              client.get_user_profile)
    safe("estatisticas_hoje",   client.get_stats,              hoje.isoformat())
    safe("estatisticas_ontem",  client.get_stats,              ontem.isoformat())

    print("\n💓 Saúde diária...")
    safe("frequencia_cardiaca_hoje",   client.get_heart_rates,     hoje.isoformat())
    safe("frequencia_cardiaca_ontem",  client.get_heart_rates,     ontem.isoformat())
    safe("estresse_hoje",              client.get_stress_data,     hoje.isoformat())
    safe("spo2_hoje",                  client.get_spo2_data,       hoje.isoformat())
    safe("hrv_hoje",                   client.get_hrv_data,        hoje.isoformat())

    print("\n😴 Sono...")
    safe("sono_ontem",   client.get_sleep_data,   ontem.isoformat())
    safe("sono_semana",  client.get_sleep_data,   (hoje - timedelta(days=7)).isoformat())

    print("\n🏃 Atividades recentes...")
    safe("atividades_recentes",  client.get_activities,  0, 20)  # últimas 20
    safe("status_treino",        client.get_training_status,    hoje.isoformat())
    safe("prontidao_treino",     client.get_training_readiness, hoje.isoformat())
    # safe("tolerancia_corrida",   client.get_running_race_prediction)  # removido: não disponível nesta versão

    print("\n📊 Métricas avançadas...")
    safe("vo2max",            client.get_max_metrics,        hoje.isoformat())
    safe("dados_fitness",     client.get_fitnessage_data,    hoje.isoformat())

    print("\n⚖️  Composição corporal...")
    safe("peso_historico",      client.get_weigh_ins,
         inicio.isoformat(), hoje.isoformat())
    safe("composicao_corporal", client.get_body_composition,
         inicio.isoformat(), hoje.isoformat())

    print("\n💧 Hidratação e passos...")
    safe("hidratacao_hoje",     client.get_hydration_data,  hoje.isoformat())
    safe("passos_historico",    client.get_steps_data,
         inicio.isoformat())

    print("\n🔥 Calorias e atividade...")
    # safe("calorias_historico",  client.get_daily_calories_consumed_and_burned)  # removido: não disponível nesta versão
    safe("intensidade_semanal", client.get_weekly_intensity_minutes,
         inicio.isoformat(), hoje.isoformat())

    return dados

# ── Salvar ────────────────────────────────────────────────────────────────────
def salvar(dados: dict):
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n✅ Dados salvos em: {OUTPUT_FILE}")
    print(f"   Próxima vez que abrir o Cowork, o Claude terá seus dados atualizados.")

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("  Garmin Connect Sync — Treinador")
    print("=" * 55)

    if "SEU_EMAIL_AQUI" in GARMIN_EMAIL:
        print("\n⚠️  Configure seu email e senha no início do script,")
        print("   ou defina as variáveis de ambiente:")
        print("   GARMIN_EMAIL=seuemail@gmail.com")
        print("   GARMIN_PASSWORD=suasenha")
        raise SystemExit(1)

    print(f"\n🔐 Autenticando como {GARMIN_EMAIL}...")
    try:
        client = fazer_login()
        print("   Login OK!")
    except Exception as e:
        print(f"\n❌ Falha no login: {e}")
        raise SystemExit(1)

    print("\n📡 Coletando dados...")
    dados = coletar_dados(client)
    salvar(dados)

    # Resumo rápido no terminal
    stats = dados.get("estatisticas_hoje") or {}
    if stats:
        print(f"\n📈 Resumo de hoje ({date.today().isoformat()}):")
        print(f"   Passos:           {stats.get('totalSteps', 'n/d'):,}")
        print(f"   Calorias ativas:  {stats.get('activeKilocalories', 'n/d')} kcal")
        print(f"   FC repouso:       {stats.get('restingHeartRate', 'n/d')} bpm")
        print(f"   Stress médio:     {stats.get('averageStressLevel', 'n/d')}")
        print(f"   Horas de pé:      {stats.get('floorsAscended', 'n/d')}")
