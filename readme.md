# Message Board
A web app that allows people to send messages to each other's Pimoroni Unicorn boards. Let's say you want to send a message to your friend, you would jump on the web app and either paint the message using colors and pixels, or you would type a message and then optionally decorate.

## Components
### Tech Stack
- geldata database
- flask server
- htmx and tailwindcss front-end
- vercel deployment
- raspberry pico
- python script controlling the boards

### Functions
- Ability to create user accounts
- Ability to add boards to your account
- Ability to add friends
- Message board web page for writing your message
- A web viewer for your messages
- A browser flashing tool to set up a new board
- Pulling new messages from the server to your board
- The ability to save messages to your account
- A cool animation around the border when there is a new message that you have to acknowledge by pushing `A`
- `C` for cycle

## To Do
- [x] Auth and user accounts
- [ ] Onboarding
  - [ ] Create username (single onboarding page that flows downward as you progress)
  - [ ] Example of how the app works
  - [ ] Add board
  - [ ] Add/invite a friend
- [ ] "Friending"
- [ ] Build UI for creating messages
- [ ] Sending messages amongst friends
- [ ] Python code for receiving and presenting messages on the Unicord board
- [ ] Flashing from the web app
