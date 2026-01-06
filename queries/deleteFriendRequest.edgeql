delete FriendRequest
filter .id = <uuid>$request_id
    and .sender.id = global current_user.id;


