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

# ── Gerar Resumo ──────────────────────────────────────────────────────────────
def gerar_resumo(dados: dict) -> dict:
    """Extrai apenas as métricas essenciais para análise diária (~15KB)."""

    def safe_get(obj, *keys, default=None):
        for k in keys:
            if not isinstance(obj, dict): return default
            obj = obj.get(k, default)
            if obj is None: return default
        return obj

    hoje = dados.get("estatisticas_hoje") or {}
    ontem = dados.get("estatisticas_ontem") or {}
    sono = safe_get(dados, "sono_ontem", "dailySleepDTO") or {}
    scores = sono.get("sleepScores") or {}
    sono_sem = safe_get(dados, "sono_semana", "dailySleepDTO") or {}
    hrv_d = dados.get("hrv_hoje") or {}
    pront = (dados.get("prontidao_treino") or [{}])
    pront = pront[-1] if pront else {}
    fc_hoje = dados.get("frequencia_cardiaca_hoje") or {}
    fitness = dados.get("dados_fitness") or {}
    comp = safe_get(dados, "composicao_corporal", "totalAverage") or {}
    peso_hist = safe_get(dados, "peso_historico", "dailyWeightSummaries") or []
    ultimo_peso = peso_hist[-1] if peso_hist else {}

    # Últimas 5 atividades — campos essenciais
    atividades = []
    for a in (dados.get("atividades_recentes") or [])[:5]:
        atividades.append({
            "nome": a.get("activityName"),
            "data": a.get("startTimeLocal"),
            "tipo": safe_get(a, "activityType", "typeKey"),
            "duracao_min": round((a.get("duration") or 0) / 60, 1),
            "distancia_km": round((a.get("distance") or 0) / 1000, 2),
            "fc_media": a.get("averageHR"),
            "fc_max": a.get("maxHR"),
            "calorias": a.get("calories"),
            "efeito_aerobico": a.get("aerobicTrainingEffect"),
            "carga_treino": a.get("activityTrainingLoad"),
            "label_treino": a.get("trainingEffectLabel"),
            "z1_min": round((a.get("hrTimeInZone_1") or 0) / 60, 1),
            "z2_min": round((a.get("hrTimeInZone_2") or 0) / 60, 1),
            "z3_min": round((a.get("hrTimeInZone_3") or 0) / 60, 1),
            "z4_min": round((a.get("hrTimeInZone_4") or 0) / 60, 1),
            "z5_min": round((a.get("hrTimeInZone_5") or 0) / 60, 1),
            "ritmo_medio_km": round(1000 / a["averageSpeed"] / 60, 2) if a.get("averageSpeed") and a["averageSpeed"] > 0 else None,
            "body_battery_delta": a.get("differenceBodyBattery"),
            "potencia_media": a.get("avgPower"),
            "vo2max": a.get("vO2MaxValue"),
        })

    resumo = {
        "sincronizado_em": dados.get("sincronizado_em"),
        "periodo": dados.get("periodo"),

        "saude_hoje": {
            "fc_repouso": hoje.get("restingHeartRate"),
            "stress_medio": hoje.get("averageStressLevel"),
            "stress_max": hoje.get("maxStressLevel"),
            "passos": hoje.get("totalSteps"),
            "calorias_ativas": hoje.get("activeKilocalories"),
            "calorias_totais": hoje.get("totalKilocalories"),
            "body_battery_carregado": hoje.get("bodyBatteryChargedValue"),
            "body_battery_gasto": hoje.get("bodyBatteryDrainedValue"),
            "minutos_moderados": hoje.get("moderateIntensityMinutes"),
            "minutos_vigorosos": hoje.get("vigorousIntensityMinutes"),
            "hidratacao_ml": safe_get(dados, "hidratacao_hoje", "valueInML"),
        },

        "saude_ontem": {
            "fc_repouso": ontem.get("restingHeartRate"),
            "stress_medio": ontem.get("averageStressLevel"),
            "passos": ontem.get("totalSteps"),
            "calorias_ativas": ontem.get("activeKilocalories"),
            "body_battery_carregado": ontem.get("bodyBatteryChargedValue"),
            "body_battery_gasto": ontem.get("bodyBatteryDrainedValue"),
        },

        "sono": {
            "data": sono.get("calendarDate"),
            "duracao_total_min": round((sono.get("sleepTimeSeconds") or 0) / 60),
            "profundo_min": round((sono.get("deepSleepSeconds") or 0) / 60),
            "rem_min": round((sono.get("remSleepSeconds") or 0) / 60),
            "leve_min": round((sono.get("lightSleepSeconds") or 0) / 60),
            "acordado_min": round((sono.get("awakeSleepSeconds") or 0) / 60),
            "numero_despertares": sono.get("awakeCount"),
            "score_geral": safe_get(scores, "overall", "value"),
            "score_classificacao": safe_get(scores, "overall", "qualifierKey"),
            "rem_percentual": safe_get(scores, "remPercentage", "value"),
            "duracao_classificacao": safe_get(scores, "totalDuration", "qualifierKey"),
            "stress_sono_classificacao": safe_get(scores, "stress", "qualifierKey"),
            "spo2_media": sono.get("averageSpO2Value"),
            "spo2_minima": sono.get("lowestSpO2Value"),
            "spo2_maxima": sono.get("highestSpO2Value"),
            "respiracao_media": sono.get("averageRespirationValue"),
            "stress_medio_sono": sono.get("avgSleepStress"),
            "fc_media_sono": sono.get("avgHeartRate"),
            "hrv_noturno": fc_hoje.get("avgOvernightHrv") or hrv_d.get("avgOvernightHrv"),
            "hrv_status": fc_hoje.get("hrvStatus") or hrv_d.get("hrvStatus"),
            "feedback": sono.get("sleepScoreFeedback"),
        },

        "sono_semana_anterior": {
            "data": sono_sem.get("calendarDate"),
            "duracao_total_min": round((sono_sem.get("sleepTimeSeconds") or 0) / 60),
            "score_geral": safe_get(sono_sem.get("sleepScores") or {}, "overall", "value"),
            "spo2_minima": sono_sem.get("lowestSpO2Value"),
        },

        "prontidao_treino": {
            "score": pront.get("score"),
            "nivel": pront.get("level"),
            "recomendacao": pront.get("feedbackShort"),
            "detalhe": pront.get("feedbackLong"),
            "fator_sono": pront.get("sleepScoreFactorFeedback"),
            "fator_hrv": pront.get("hrvFactorFeedback"),
            "fator_recuperacao": pront.get("recoveryTimeFactorFeedback"),
            "fator_carga": pront.get("acwrFactorFeedback"),
            "fator_stress": pront.get("stressHistoryFactorFeedback"),
            "hrv_semanal": pront.get("hrvWeeklyAverage"),
            "carga_aguda": pront.get("acuteLoad"),
            "recuperacao_necessaria_min": pront.get("recoveryTime"),
        },

        "composicao_corporal": {
            "peso_kg": round((ultimo_peso.get("latestWeight", {}) or {}).get("weight", 0) / 1000, 1) if ultimo_peso else None,
            "data_peso": safe_get(ultimo_peso, "latestWeight", "calendarDate"),
            "gordura_percentual": comp.get("bodyFatPercentage"),
            "massa_muscular_kg": comp.get("muscleMassInGrams", 0) / 1000 if comp.get("muscleMassInGrams") else None,
        },

        "fitness": {
            "vo2max": safe_get(dados, "perfil", "userData", "vo2MaxRunning"),
            "fitness_age": fitness.get("fitnessAge"),
            "fitness_age_cronologica": fitness.get("chronologicalAge"),
            "fc_repouso_historico": safe_get(fitness, "components", "rhr", "value"),
            "dias_vigorosos_media": safe_get(fitness, "components", "vigorousDaysAvg", "value"),
            "minutos_vigorosos_media": safe_get(fitness, "components", "vigorousMinutesAvg", "value"),
            "gordura_percentual_fitness": safe_get(fitness, "components", "bodyFat", "value"),
            "fc_limiar": safe_get(dados, "perfil", "userData", "lactateThresholdHeartRate"),
            "ftp": safe_get(dados, "perfil", "userData", "functionalThresholdPower"),
        },

        "atividades_recentes": atividades,
    }

    return resumo


# ── Salvar ────────────────────────────────────────────────────────────────────
def salvar(dados: dict):
    # Arquivo completo
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n✅ Dados completos salvos em: {OUTPUT_FILE}")

    # Arquivo resumo (para GitHub/acesso remoto)
    resumo = gerar_resumo(dados)
    resumo_file = OUTPUT_DIR / "garmin_resumo.json"
    with open(resumo_file, "w", encoding="utf-8") as f:
        json.dump(resumo, f, ensure_ascii=False, indent=2, default=str)
    print(f"✅ Resumo salvo em: {resumo_file}")
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
        passos = stats.get('totalSteps')
        print(f"   Passos:           {passos:,}" if passos else "   Passos:           n/d")
        print(f"   Calorias ativas:  {stats.get('activeKilocalories', 'n/d')} kcal")
        print(f"   FC repouso:       {stats.get('restingHeartRate', 'n/d')} bpm")
        print(f"   Stress médio:     {stats.get('averageStressLevel', 'n/d')}")
        print(f"   Horas de pe:      {stats.get('floorsAscended', 'n/d')}")
