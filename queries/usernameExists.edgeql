select exists (
  select User
  filter .username = <str>$username
);