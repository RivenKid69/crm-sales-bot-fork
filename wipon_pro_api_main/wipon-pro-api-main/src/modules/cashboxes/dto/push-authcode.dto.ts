import { IsNotEmpty, IsPhoneNumber, IsString } from 'class-validator';

export class PushAuthcodeDto {
  @IsNotEmpty()
  @IsString()
  @IsPhoneNumber('KZ')
  phone_number: string;

  @IsNotEmpty()
  @IsString()
  auth_code: string;
}
