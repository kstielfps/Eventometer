# 📖 Guia do Membro — Sistema de Booking ATC

Bem-vindo ao **Eventometer**! Este guia vai te ajudar a entender como aplicar para posições ATC em eventos, como cancelar uma aplicação, e como funcionam as notificações que você vai receber.

---

## 📋 Pré-requisitos

Antes de usar o bot, certifique-se de que:

1. **Sua conta VATSIM está vinculada ao Discord.**
   Acesse [my.vatsim.net](https://my.vatsim.net) e vincule sua conta do Discord na seção de configurações.
2. Você é membro do servidor Discord onde o bot está ativo.

> **Sem vínculo, o bot não conseguirá te identificar.** Se você tentar usar o comando e receber uma mensagem de erro, verifique se o vínculo está ativo em my.vatsim.net.

---

## ✈️ Como Aplicar para uma Posição ATC

Para aplicar para controlar em um evento, siga estes passos:

### Passo 1 — Abrir o menu de eventos

Digite o comando `/eventos` em qualquer canal do servidor onde o bot está presente.

> A resposta será **visível apenas para você** (mensagem efêmera), então pode usar sem medo!

### Passo 2 — Identificação automática

O bot vai identificar automaticamente a sua conta VATSIM e mostrar:
- Seu **CID** (identificação VATSIM)
- Seu **Rating** atual (S1, S2, S3, C1, etc.)

### Passo 3 — Selecionar o evento

Um menu suspenso (dropdown) vai aparecer com todos os **eventos abertos** para booking. Escolha o evento do qual deseja participar.

> Se não houver eventos abertos, o bot vai te avisar. Fique de olho nos anúncios do servidor!

### Passo 4 — Selecionar blocos de horário

Agora você vai ver os blocos de horário disponíveis para o evento (por exemplo, `Bloco 1: 22:00–23:00z`, `Bloco 2: 23:00–00:00z`).

- **Você pode selecionar múltiplos blocos** — marque todos os horários em que você está **disponível** para controlar.
- Apenas blocos que ainda possuem posições disponíveis para o seu rating serão mostrados.

### Passo 5 — Selecionar posições

Uma lista de posições compatíveis com o seu rating vai aparecer. Você verá apenas as posições para as quais o seu rating permite aplicar.

- **Você pode selecionar mais de uma posição** — isso aumenta suas chances de ser selecionado!
- Cada posição mostra o rating mínimo necessário.

### Passo 6 — Confirmação da aplicação

Pronto! 🎉 O bot vai mostrar um **resumo** com:
- O nome do evento
- As posições selecionadas
- Os blocos de horário escolhidos

Sua aplicação está registrada e agora é só aguardar. Se você for selecionado para alguma posição, receberá uma notificação!

---

## 🗑️ Como Revogar (Cancelar) uma Aplicação

Mudou de planos? Sem problemas! Veja como cancelar:

### Passo 1 — Abrir o menu de revogação

Digite o comando `/revogar` em qualquer canal do servidor.

> Assim como o `/eventos`, a resposta é **visível apenas para você**.

### Passo 2 — Selecionar o evento

Um menu suspenso vai mostrar todos os eventos nos quais você possui aplicações ativas. Selecione o evento que deseja cancelar.

### Passo 3 — Confirmação automática

Ao selecionar o evento, **todas** as suas aplicações naquele evento serão revogadas de uma vez, e você receberá uma mensagem de confirmação.

> ⚠️ **Atenção:** Se você já tiver sido **confirmado** para uma posição e revogar, isso será registrado como **No-Show** no seu perfil, e os administradores serão notificados. Revogue apenas se realmente necessário!

---

## 💬 Como Funcionam as Notificações

Ao longo do processo de booking, o bot poderá te enviar notificações importantes, como:

- 🎉 **Seleção** — Quando você for selecionado para uma posição (com botão para confirmar participação)
- 🔔 **Lembrete** — Um lembrete antes do evento para confirmar sua presença
- 📋 **Rejeição** — Se todas as posições já foram preenchidas e você não foi selecionado

### Via Mensagem Direta (DM)

Por padrão, o bot tentará enviar as notificações **por mensagem direta (DM)**.

**Para que isso funcione, você precisa ter habilitada a opção de receber DMs de membros do servidor.**

#### Como ativar DMs de membros do servidor:

1. Abra o **Discord** e vá até o servidor onde o bot está.
2. Clique no **nome do servidor** no topo (ou clique com o botão direito nele).
3. Selecione **Configurações de Privacidade** (Privacy Settings).
4. Ative a opção **"Mensagens diretas de membros do servidor"** (Direct Messages from Server Members).
5. Salve as alterações.

> 💡 **Dica:** Recomendamos manter essa opção ativada para uma experiência melhor e mais rápida!

### Via Canal Privado no Servidor (Fallback)

Se as suas DMs estiverem **desativadas** (ou se o bot não conseguir te enviar mensagens privadas), não se preocupe! O sistema possui um mecanismo alternativo:

1. O bot vai tentar te enviar uma DM.
2. Se não conseguir após **2 tentativas**, um **canal de texto privado** será criado automaticamente no servidor, visível **apenas para você e os administradores**.
3. A notificação (incluindo botões de confirmação) será enviada **nesse canal**.
4. Após você confirmar sua participação pelo canal, ele será **deletado automaticamente** em alguns segundos.

> 📌 **Resumindo:**
> - ✅ **DMs ativadas** → Você recebe tudo por mensagem privada, de forma rápida e direta.
> - 🔒 **DMs desativadas** → Um canal privado aparecerá no servidor para você receber as notificações e confirmar presença.

---

## ❓ Perguntas Frequentes

**P: Posso aplicar para mais de um evento ao mesmo tempo?**
R: Sim! Basta usar `/eventos` novamente e selecionar outro evento.

**P: Posso aplicar para múltiplas posições no mesmo evento?**
R: Sim! Na etapa de seleção de posições, você pode marcar várias. Isso aumenta suas chances de ser alocado.

**P: Como sei se fui selecionado?**
R: Você receberá uma notificação (via DM ou canal privado) com um botão para **confirmar sua participação**.

**P: E se eu esquecer de confirmar?**
R: Os administradores podem te enviar um **lembrete** adicional antes do evento. Mas é importante ficar de olho nas mensagens!

**P: Revoguei por engano. O que faço?**
R: Se o evento ainda estiver aberto, você pode aplicar novamente usando `/eventos`. Se já tinha sido confirmado, entre em contato com um administrador.

**P: O que é No-Show?**
R: Se você **já estava confirmado** para uma posição e cancela a aplicação, isso é considerado um No-Show. Ele fica registrado no seu perfil e os administradores são notificados. Revogue com antecedência sempre que possível!

---

## 📝 Resumo Rápido dos Comandos

| Comando | O que faz |
|---|---|
| `/eventos` | Mostra os eventos abertos e inicia o fluxo de aplicação para posições ATC |
| `/revogar` | Revoga (cancela) todas as suas aplicações em um evento selecionado |

---

Bons voos e boas sessões de controle! 🛫💙
