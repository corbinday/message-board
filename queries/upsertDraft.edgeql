with
  user := assert_single(
    select User
    filter assert_single(.identity = global ext::auth::ClientTokenIdentity)
  ),
  existing := (
    select DraftGraphic
    filter .creator = user
      and (
        (.active_board.id = <optional uuid>$board_id) if exists <optional uuid>$board_id
        else not exists .active_board
      )
    limit 1
  ),
  upserted := (
    update existing
    set {
      binary := <bytes>$data,
      frames := <int16>$frames,
      frame_delay_ms := <int16>$frame_delay_ms,
      size := <BoardType>$size,
      updated_at := datetime_of_statement()
    }
  ) if exists existing else (
    insert DraftGraphic {
      binary := <bytes>$data,
      frames := <int16>$frames,
      frame_delay_ms := <int16>$frame_delay_ms,
      size := <BoardType>$size,
      creator := user,
      active_board := (select Board filter .id = <optional uuid>$board_id)
    }
  )
select upserted { id, frames, frame_delay_ms, updated_at }
