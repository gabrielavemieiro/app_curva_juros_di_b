# Monitor de Curva de Juros - DI Futuro 
Este projeto é um dashboard interativo desenvolvido em Python na intenção de monitorar em tempo real a *Estrutura a Termo das Taxas de Juros (ETTJ)* do Brasil. A ferramenta processa dados de contratos de DI Futuro diretamente da API da B3, aplicando métodos matemáticos de interpolação e cálculo de taxas a termo (*forwards*).



## Roadmap Técnico
O desenvolvimento do dashboard seguiu uma trajetória focada em escalabilidade e precisão técnica, superando o desafio da atualização dos dados quase em real time. Abaixo estão as principais decisões de engenharia:

### 1. Coleta e Tratamento de Dados
* **Integração com B3:** Consumo direto via API das cotações do DI1. Não há armazenamento em banco de dados.
* **Resiliência da Aplicação:** Implementação de um bloco `try-except` para evitar que falhas de conexão ou instabilidades na API interrompam a execução do serviço.
* **Otimização de Parsing:** Priorização do uso de List Comprehension para transformar o JSON de resposta em estruturas de dados (garante maior eficiência quando comparado ao loops tradicionais).

### 2. Eficiência de Processamento
* **Vetorização:** O cálculo de Dias Úteis (DU) entre a data corrente e o vencimento dos contratos utiliza operações vetorizadas do `numpy` (`busday_count`). Isso processa toda a série temporal de forma significativamente mais rápida que o método `.apply()` do pandas (utilizado anteriormente a refatoração).
* **Gestão de Feriados:** Integração com a biblioteca `holidays` para garantir a contagem exata de dias úteis conforme o calendário brasileiro até 2040.

### 3. Escalabilidade e Performance do Dashboard
* **Cache Multinível:**
    * *Global:* Armazenamento dos feriados (cache de longo prazo).
    * *Sessão:* Implementação de `@st.cache_data` com `ttl=30` e `max_entries=1` para as requisições da B3. Isso garante que, em acessos simultâneos, o servidor processe a lógica apenas uma vez a cada 30 segundos, servindo os dados em cache para os demais usuários.
* **Atualização por Fragmentos:** Utilização do decorador `@st.fragment`. Diferente de um *autorefresh* global, esta técnica permite atualizar apenas os componentes de dados e gráficos sem recarregar elementos estáticos da interface (sidebar, títulos), proporcionando uma experiência de usuário fluida.

### 4. Inteligência Matemática e Visual
* **Interpolação Cubic Spline:** Implementação da técnica *Natural Cubic Spline* via `scipy` para suavizar a curva entre os vértices reais, permitindo a estimativa de taxas para prazos não negociados.
* **Expectativas Forward:** Cálculo das taxas a termo diretamente entre os vértices da B3, apresentadas em um gráfico de barras para evidenciar a expectativa de juros em intervalos específicos.
* **Refinamento Visual:** Ajuste dinâmico do eixo Y para focar na região de liquidez (ex: iniciando em 10% conforme o cenário de mercado) e verticalização das labels do eixo X para suportar o alto volume de contratos.

---

## Bibliotecas Utilizadas

| Biblioteca | Função Principal |
| :--- | :--- |
| **Streamlit** | Framework para interface web e gestão de estado. |
| **Pandas & Numpy** | Manipulação de dados e cálculos vetorizados. |
| **Requests** | Comunicação com a API da B3. |
| **Holidays** | Gestão de feriados brasileiros. |
| **SciPy** | Suporte matemático para a interpolação *CubicSpline*. |
| **Plotly** | Criação de gráficos interativos. |

---

## Próximos Passos
*  **Deploy em Produção:** Publicação do dashboard para suportar 5 usuários simultâneos.
*  **Modularização do Sistema:** Migração completa da lógica de interface para `app.py` e das lógicas de negócio/matemática para diretórios específicos, visando facilitar a manutenção e testes unitários.
* **Ajustes Finos de UI:** Implementação de temas escuros/claros adaptativos e exportação de dados tratados em formato CSV/Excel.
* **Indicadores Adicionais:** Inclusão de projeções de reuniões do COPOM diretamente na curva curta e adição do calendário dos principais eventoss econômicos.

---

##  Execução Local

1.  **Instalar as dependências:**
    ```bash
    pip install -r requirements.txt
    ```

2.  **Execute o comando:**
    ```bash
    streamlit run app.py
    ```

---
*Desenvolvido por Gabriela Vemieiro*
