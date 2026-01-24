I completely scrapped all the junk other models generated. Let's take this slower and more thoughtfully. I want to design a black box pixel-editor element. In needs to have some 

Is there a way with htmx to run js to get the payload for an hx-post? I want to call the pixel-editor api to grab the binary data via htmx so that my submit and save buttons can live outside of the editor.

Now that the editor is working well, I need to make sure that it has an API so that I can insert it into different contexts well. I have three scenarios in mind where I would use it: 
 1. The first is for creating the user's avatar. The pixel editor would be 16x16 and it would not allow for adding frames. Avatars are static.
 2. The second scenario is sending a message. The user would be able to do either a static animation or an animation. The editor would be generated based on the board of the friend to whom the user wants to send a message. So the friend needs to be selected first, and then the friend's boards from the available options. Then, a pixel editor element with the height and width of the friend's board needs to be created. In this scenario, animations would be allowed.
 3. The third scenario is where the user just makes art. They would select from any size they wish, however, if they want to enable live preview where the art they are working on is sent in near real time (facilitate by ably) to a board they own, they have to pick a size that matches a board they own. So in this scenario, the logic outside of the editor would check to see if the user has a board that works for live preview and then offer it/them as an option for live preview. Then, it would listen to events emitted to the editor for data changed (similar to autosave) and then send a message through ably which the user's board would be subscribed to so it could pull the new image/animation data.


Let's fix the PNG upload button. It doesn't do anything after you select a file to upload. What I would like it to do is ask the user if they want to replace just the current frame or the entire project (but only ask if the editor/draft has data) and then let them edit the upload there in the editor before "finishing". If it's blank, just load the PNG. It will need to make sure that the dimensions match up with the board size. Also, I want it to try to detect whether the user is trying to import a spritesheet where the PNG is really tall or really short but matches one of the dimensions. That way the user could import an animation they created somewhere else and then modify it. I think this means we will want button to reverse frame order. Also, let's make it so the user can drag and drop frames to change the order as well. Also, the UI still let's me set the delay to less than 100ms. Let's make sure to put a cap on that. Go into planning mode before you implement this stuff so you don't miss anything.


Let's enter planning mode and solve the following issues:
* In-line styling: I am getting errors in the browser because the pixel editor is still trying to use in-line styling when it swaps out the grid when a user clicks one of the size buttons on /app/art/create. Let's do an audit again of all in-line styling and switch to TailwindCSS (preferred) or styles in style.css if tailwind won't work. While you are at it, let's audit the style.css file to see where we can leverage tailwind as well following a pattern like this: 
```css
.myclass {
  @apply bg-white;
}
```
I want to use as much tailwindcss as possible.

* PNG upload button issues: I am getting errors in the browser that PNG upload fails. My testing scenario was to try to load img/check.png into the 16x16 editor. This was the error: 
  ```
  create:1 Loading the image 'blob:http://localhost:3000/29571f1e-6bb0-4cff-8337-cb9c9611f9ce' violates the following Content Security Policy directive: "img-src 'self' https://gj6vlq8nqjtpg33c.public.blob.vercel-storage.com/". The action has been blocked.
  ```
* "Finish and Save" button: The Finish and Save button does not work. I have discovered two errors. The first is when you first load the editor page. I get a 500 error with this log:
```
ERROR in app: Error finishing draft: cannot reference correlated set 'draft.frames' here
   ┌─ query:19:16
   │ 
19 │             ) if draft.frames > 1 else (
   │                  ^^^^^^^^^^^^ error
```
The second error is that the button is entirely grayed out sometimes and the cursor is the blocked/error cursor. I haven't been able to pinpoint when it becomes grayed out.
* Another issue is that the frame delay ms rate doesn't seem to be saving to the database when I change it. That should trigger an autosave as well, with at least 500ms of debouncing.
* Another issue is that the size in the database is not being saved properly. All my DraftGraphic data shows the board size as Galactic. 16x16 is Stellar, 32x32 is Cosmic, and 53x11 is Galactic. When the user updates what size of board they are drafting on, that needs to be reflected in the database as well. Let's make sure everything is synching properly to the database (board type, frame refresh rate, and frame count).
* Let's add a sub-view to the app dashboard under "Your Art" where Drafts appear. In the draft editor itself, let's add an option to delete a draft and remove it fully from the database. Let's also add the delete option to art pieces as well.