# 📖 Guia de Uso — Eventometer Bot

---

## 📌 Sumário

- [1. Flow do Administrador — Fluxo Normal](#1-flow-do-administrador--fluxo-normal)
- [2. Flow do Administrador — Desistência / Troca de Controlador](#2-flow-do-administrador--desistência--troca-de-controlador)
- [3. Flow do Usuário — Como Fazer uma Reserva](#3-flow-do-usuário--como-fazer-uma-reserva)
- [4. Flow do Usuário — Como Revogar uma Reserva](#4-flow-do-usuário--como-revogar-uma-reserva)

---

## 1. Flow do Administrador — Fluxo Normal

Este é o passo a passo completo para configurar e gerenciar um evento do início ao fim.

### Passo 1 — Importar o Evento do VATSIM

```
/importar event_id:<ID_DO_EVENTO_VATSIM>
```

- O bot busca os dados do evento na API do VATSIM (nome, data, horário, banner, etc.)
- Um **modal** aparecerá pedindo a **duração de cada bloco** (em minutos, ex: `60`)
- Os blocos de horário são gerados automaticamente com base na duração do evento
- Se o modal não abrir (ex: Discord Web), use o comando alternativo:
  ```
  /configurar_blocos event_id:<ID> duracao:<MINUTOS>
  ```

### Passo 2 — Adicionar ICAOs ao Evento

```
/adicionar_icao event_id:<ID> icaos:SBBR,SBGR,SBSP
```

- ICAOs são os aeródromos do evento (separados por vírgula)
- Cada ICAO será associado ao evento para receber posições ATC

### Passo 3 — Adicionar Posições aos ICAOs

```
/adicionar_posicao event_id:<ID>
```

- Abre uma interface interativa com dois dropdowns:
  1. **Selecione o ICAO** (ex: `SBBR`)
  2. **Selecione as posições** (multi-seleção, ex: `TWR`, `APP`, `CTR`)
- As posições vêm dos **templates** cadastrados no Django Admin
- Repita para cada ICAO do evento

### Passo 4 — Abrir o Evento para Bookings

```
/abrir_bookings event_id:<ID>
```

- Muda o status do evento para **OPEN** (aberto para receber aplicações)
- O bot verifica se há blocos de horário e posições configuradas antes de abrir
- **Pré-requisitos:** blocos configurados + posições adicionadas

### Passo 5 — Anunciar o Evento no Canal

```
/anunciar canal:#nome-do-canal
```

- Selecione o evento na lista de eventos abertos
- O bot envia um **embed rico** no canal com:
  - Nome, data, horário e banner do evento
  - Posições disponíveis
  - Blocos de horário
  - Botão **"📋 Aplicar para Posição"** para os usuários
- Se houver um cargo configurado (`DISCORD_ANNOUNCE_ROLE_ID`), o bot menciona o cargo

### Passo 6 — Acompanhar as Aplicações

```
/aplicacoes event_id:<ID>
```

- Exibe um resumo de todas as aplicações agrupadas por posição e bloco
- Status exibidos:
  - 🟡 **Pendente** — aguardando seleção
  - 🔒 **Selecionado (Locked)** — selecionado, aguardando confirmação do usuário
  - ✅ **Confirmado** — usuário confirmou participação
  - ✅✅ **Confirmação Final** — confirmação final (pré-evento)

```
/status_evento
```

- Visão geral rápida de todos os eventos abertos (total de aplicações e travadas)

### Passo 7 — Selecionar Controladores

```
/selecionar event_id:<ID>
```

- Interface interativa em 3 etapas:
  1. **Selecione a posição** (ex: `SBBR_TWR`)
  2. **Selecione o bloco de horário** (ex: `Bloco 1: 20:00–21:00z`)
  3. **Selecione o controlador** (mostra CID, nome e rating)
- Ao selecionar:
  - O controlador é **travado (locked)** na posição+bloco
  - Aplicações do **mesmo usuário** para **outras posições no mesmo bloco** são rejeitadas automaticamente
  - Aplicações de **outros usuários** para a **mesma posição+bloco** são rejeitadas automaticamente
  - O embed do anúncio é atualizado mostrando o ATC selecionado
  - Uma **DM de notificação** é enviada ao controlador com um botão "✅ Confirmar Participação"
- Repita `/selecionar` para cada posição+bloco

### Passo 8 — Fechar as Bookings

```
/fechar event_id:<ID>
```

- Rejeita todas as aplicações **pendentes** restantes
- Muda o status do evento para **LOCKED** (posições travadas)
- Atualiza o embed do anúncio

### Passo 9 — Enviar Notificações de Rejeição

```
/rejeitar event_id:<ID>
```

- Enfileira DMs de rejeição para todos os usuários não selecionados
- Apenas envia para quem **não foi aceito** em nenhuma posição do evento
- As mensagens são enviadas automaticamente pelo loop de notificações

### Passo 10 — Enviar Lembretes (Pré-Evento)

```
/lembrete event_id:<ID>
```

- Enfileira DMs de lembrete para todos os controladores selecionados/confirmados
- O lembrete inclui um botão de **"✅ Confirmação Final"**
- Quando o controlador clica, o status muda para **FULL_CONFIRMED**

---

### 📊 Resumo do Fluxo Admin (Normal)

```
/importar → /adicionar_icao → /adicionar_posicao → /abrir_bookings → /anunciar
    → /aplicacoes → /selecionar → /fechar → /rejeitar → /lembrete
```

---

## 2. Flow do Administrador — Desistência / Troca de Controlador

### Cenário A: Controlador desiste **antes** do evento

Quando um controlador usa `/revogar` (veja seção 4), o comportamento depende do status:

| Status da Aplicação | O que acontece |
|---------------------|---------------|
| **Pendente** | Aplicação é deletada |
| **Locked** (selecionado, mas não confirmou) | Status muda para **CANCELLED** |
| **Confirmado / Confirmação Final** | Status muda para **NO_SHOW**, admins recebem alerta por DM |

Se houver **no-show** (desistência após confirmação):
- Todos os admins recebem uma **DM de alerta** com detalhes das posições afetadas
- O embed do anúncio é atualizado (posição volta a aparecer como disponível)
- O controlador recebe um registro de no-show no perfil

### Cenário B: Admin precisa trocar/substituir um controlador

Use o comando de **seleção de reserva**:

```
/selecionarreserva event_id:<ID>
```

- Interface interativa em 3 etapas:
  1. **Selecione a posição** que precisa de controlador (mostra apenas posições com blocos sem controlador)
  2. **Selecione o bloco** sem controlador
  3. **Selecione o controlador reserva** da lista de candidatos elegíveis
- Candidatos elegíveis incluem:
  - Todos os usuários que aplicaram para o evento (incluindo rejeitados anteriormente)
  - Filtrados por rating mínimo da posição
  - Excluindo quem já está alocado naquele bloco de horário
- Ao selecionar:
  - Se havia um controlador anterior, ele é **rejeitado** e recebe +1 cancelamento
  - O novo controlador é **travado (locked)** na posição
  - Uma DM de notificação é enviada ao novo controlador
  - O embed do anúncio é atualizado

### 📊 Resumo do Fluxo de Substituição

```
Desistência detectada (via /revogar ou admin identifica)
    → /selecionarreserva event_id:<ID>
    → Seleciona posição → Seleciona bloco → Seleciona novo controlador
    → Notificação enviada automaticamente
```

---

## 3. Flow do Usuário — Como Fazer uma Reserva

### Opção A: Via comando `/eventos`

1. **Digite `/eventos`** em qualquer canal onde o bot esteja presente
2. O bot identifica sua conta VATSIM automaticamente (via Discord vinculado ao VATSIM)
3. Você verá suas informações: **CID** e **Rating**
4. **Selecione um evento** no dropdown (mostra apenas eventos abertos)
5. **Selecione os blocos de horário** em que você está disponível (pode selecionar múltiplos)
   - Apenas blocos com posições disponíveis para seu rating são mostrados
6. **Selecione as posições** que deseja aplicar (pode selecionar múltiplas)
   - Apenas posições compatíveis com seu rating são exibidas
   - Apenas posições com vagas nos blocos selecionados aparecem
7. **Pronto!** Você verá um resumo da aplicação com as posições e blocos selecionados

### Opção B: Via botão no anúncio do evento

1. Encontre o **anúncio do evento** no canal do Discord
2. Clique no botão **"📋 Aplicar para Posição"**
3. O bot identifica sua conta VATSIM automaticamente
4. **Selecione os blocos de horário** disponíveis
5. **Selecione as posições** desejadas
6. **Pronto!** Resumo da aplicação exibido

### O que acontece depois?

- Sua aplicação fica com status **Pendente** (🟡)
- Um administrador irá selecionar os controladores para cada posição
- Se você for selecionado:
  - Recebe uma **DM** com os detalhes e um botão **"✅ Confirmar Participação"**
  - Clique no botão para confirmar
- Antes do evento, você pode receber um **lembrete** com botão de **"✅ Confirmação Final"**
- Se não for selecionado:
  - Você receberá uma **DM de rejeição** informando que as vagas foram preenchidas

### ⚠️ Observações Importantes

- Sua conta Discord **precisa estar vinculada** ao VATSIM em https://my.vatsim.net
- Você só verá posições compatíveis com seu **rating atual**
- Você **não** pode ser alocado em duas posições no **mesmo bloco de horário**
- Todas as interações são **efêmeras** (apenas você vê as mensagens)

---

## 4. Flow do Usuário — Como Revogar uma Reserva

### Passo a Passo

1. **Digite `/revogar`** em qualquer canal onde o bot esteja presente
2. O bot mostra uma lista de **eventos onde você tem aplicações ativas**
3. **Selecione o evento** do qual deseja revogar suas aplicações
4. **Todas** as suas aplicações naquele evento serão revogadas

### O que acontece ao revogar?

Depende do status das suas aplicações:

| Seu Status | O que acontece ao revogar |
|------------|--------------------------|
| **Pendente** | Aplicação é simplesmente **deletada** (sem consequências) |
| **Selecionado (Locked)** | Status muda para **Cancelado** — contabilizado como cancelamento no perfil |
| **Confirmado / Confirmação Final** | Status muda para **No-Show** — contabilizado como no-show no perfil, **admins são notificados** |

### ⚠️ Consequências

- **Revogar aplicações pendentes**: Sem consequências. Livre para reaplicar.
- **Revogar após ser selecionado**: +1 cancelamento no seu perfil. A posição fica vaga para o admin preencher com outro controlador.
- **Revogar após confirmação**: +1 no-show no seu perfil. Todos os admins recebem um **alerta por DM** com detalhes das posições afetadas. A posição fica vaga.

### 💡 Dica

Se você precisa cancelar, faça o mais cedo possível (enquanto a aplicação ainda está **pendente**) para evitar registros negativos no perfil e facilitar a logística do evento.

---

## 📋 Referência Rápida dos Comandos

### Comandos de Usuário

| Comando | Descrição |
|---------|-----------|
| `/eventos` | Ver eventos abertos e aplicar para posições ATC |
| `/revogar` | Revogar todas as suas aplicações de um evento |

### Comandos de Admin

| Comando | Descrição |
|---------|-----------|
| `/importar event_id:<ID>` | Importar evento do VATSIM |
| `/configurar_blocos event_id:<ID> duracao:<MIN>` | Configurar blocos de horário |
| `/adicionar_icao event_id:<ID> icaos:<ICAOS>` | Adicionar ICAOs ao evento |
| `/adicionar_posicao event_id:<ID>` | Adicionar posições aos ICAOs |
| `/abrir_bookings event_id:<ID>` | Abrir evento para receber bookings |
| `/anunciar canal:#canal` | Anunciar evento em um canal |
| `/status_evento` | Ver resumo rápido de eventos abertos |
| `/aplicacoes event_id:<ID>` | Ver todas as aplicações de um evento |
| `/selecionar event_id:<ID>` | Selecionar controladores para posições |
| `/selecionarreserva event_id:<ID>` | Selecionar controlador reserva |
| `/fechar event_id:<ID>` | Fechar bookings e rejeitar pendentes |
| `/rejeitar event_id:<ID>` | Enviar DMs de rejeição |
| `/lembrete event_id:<ID>` | Enviar lembretes de confirmação final |

---

## 🔄 Diagrama do Ciclo de Vida de uma Aplicação

```
PENDENTE (🟡)
  │
  ├──[Admin seleciona]──→ LOCKED (🔒) ──[Usuário confirma]──→ CONFIRMED (✅)
  │                          │                                     │
  │                          │                         [Admin envia lembrete]
  │                          │                                     │
  │                          │                        [Usuário confirma final]
  │                          │                                     │
  │                          │                              FULL_CONFIRMED (✅✅)
  │                          │
  │                    [Usuário revoga]
  │                          │
  │                      CANCELLED
  │
  ├──[Admin fecha / Auto-rejeição]──→ REJECTED (❌)
  │
  └──[Usuário revoga]──→ (deletada)

CONFIRMED / FULL_CONFIRMED
  │
  └──[Usuário revoga]──→ NO_SHOW (⚠️) + Alerta aos admins
```
