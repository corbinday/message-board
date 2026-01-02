# Message Board
A web app that allows people to send messages to each other's Pimoroni Unicorn boards. Let's say you want to send a message to your friend, you would jump on the web app and either paint the message using colors and pixels, or you would type a message and then optionally decorate.

# Components
## Board Components
Space Unicorn Variants:
* Stellar: 16 x 16 pixels
* Galactic: 53 x 11 pixels
* Cosmic: 32 x 32 pixels

## Web Components
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
- [x] Landing page
- [x] Hero Logo
- [x] Mini Logo (PMB)
- [ ] Onboarding
  - [ ] Create username (single onboarding page that flows downward as you progress)
  - [ ] Example of how the app works
  - [x] Add board
  - [ ] Add/invite a friend
- [ ] "Friending"
  - [ ] Create an Avatar on start (16 x 16)
- [ ] Build UI for creating messages
- [ ] Sending messages amongst friends
- [ ] Python code for receiving and presenting messages on the Unicor board
- [ ] Flashing from the web app

# Home Features
* Registered Boards
* Friends
* Messages 
  * Feed Preview
  * Start with a default hello message for all users
  * Create message
* 


# Landing Page Ideas
I am building an app where a user can draw on a grid of pixels that represents a Pimoroni Space Unicorn board and send it to an actual board in the real world. The app is called "Pico Message Board" and I am trying to design the landing page and some other features that will persist throughout the user experience.

I want the background layer to be a static (non-scrolling) pixel grid with the rain effect and the hover effect. The content layer will scroll over the top of that.

The background will be full black and then the "pixel off" color will be a slightly lighter black so the entire page looks like a grid but not overbearingly so, with the full black coming through in the gaps between the pixels. I want there to be a rain effect which randomly activates pixels in an irregular pattern. The rain effect should activate about 5% of the total pixel count so that it doesn't get lost in a big canvas. Make the coverage a variable so I can adjust it easily. The rain effect should activate white, primary and secondary colors at random.

There should also be a mouse-hover effect that leaves behind a trail where the mouse has been that fades away. The trail should be RGB red, and start at about 80% opacity.

When the page is shrunk I want to clean up unused pixels to make the page more efficient. The minimum width the page can have is 53 pixels so the background layer needs to scale down so they fit. Any pixel art content generated in the content layer needs to have the same pixel dimensions as the background. Any pixel art in the content layer needs to align with the pixels underneath so they look integrated so scrolling needs to snap. A tearing effect would be cool so that any scrolling of the content layer would leave behind a disappearing trace (like the hover effect) but only from pixel art items.

Text in the content layer needs to have a frosty, transparent background so that any pixels that light up underneath look like they are coming through a diffuser.

I am using TailwindCSS in my project, so use that whenever possible. I am also using Flask templates, so the background logic should be baked into a base template that the content layers extend.