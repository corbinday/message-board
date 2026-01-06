delete FriendRequest
filter .id = <uuid>$request_id
    and .recipient.id = global current_user.id;


