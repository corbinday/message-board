CREATE MIGRATION m1v7v25hz3idz2vyljj54w6rjgex24pjibae7gn7jqcxwfbgx4ad3a
    ONTO initial
{
  CREATE EXTENSION pgcrypto VERSION '1.3';
  CREATE EXTENSION auth VERSION '1.0';
  CREATE FUTURE no_linkful_computed_splats;
  CREATE TYPE default::User {
      CREATE MULTI LINK identity: ext::auth::Identity {
          CREATE CONSTRAINT std::exclusive;
      };
      CREATE REQUIRED PROPERTY email: std::str {
          CREATE CONSTRAINT std::exclusive;
      };
      CREATE REQUIRED PROPERTY firstName: std::str;
      CREATE REQUIRED PROPERTY lastName: std::str;
  };
};
