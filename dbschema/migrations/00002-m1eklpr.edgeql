CREATE MIGRATION m1eklprw7x66mxihzhslmvuzlmfwd2kvedokqqn4drp3u6xm7e6byq
    ONTO m1v7v25hz3idz2vyljj54w6rjgex24pjibae7gn7jqcxwfbgx4ad3a
{
  ALTER TYPE default::User {
      CREATE PROPERTY username: std::str;
      DROP PROPERTY firstName;
      DROP PROPERTY lastName;
  };
  CREATE GLOBAL default::current_user := (std::assert_single((SELECT
      default::User
  FILTER
      (.identity = GLOBAL ext::auth::ClientTokenIdentity)
  )));
};
