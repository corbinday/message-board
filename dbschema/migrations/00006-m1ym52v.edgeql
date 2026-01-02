CREATE MIGRATION m1ym52v55a5odbkq7j4lyboi2i66buyt4q2n5ighmjr7hqrb3ci4za
    ONTO m1xaj6bljuymkinojpxtylvozyxwyswknpdsf52ztmsxdmtwo2ei6a
{
  CREATE SCALAR TYPE default::BoardType EXTENDING enum<Stellar, Galactic, Cosmic>;
  CREATE TYPE default::Board {
      CREATE REQUIRED LINK owner: default::User;
      CREATE REQUIRED PROPERTY boardType: default::BoardType;
      CREATE PROPERTY name: std::str;
      CREATE PROPERTY secret_key_hash: std::str;
  };
};
