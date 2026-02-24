import { IsIn, IsInt, IsNotEmpty, IsOptional, IsPhoneNumber, IsString } from 'class-validator';

export class PostCallbackDto {
  @IsNotEmpty()
  @IsInt()
  id: number;

  @IsNotEmpty()
  @IsString()
  @IsPhoneNumber('KZ')
  phone: string;

  @IsNotEmpty()
  @IsString()
  status: string;

  @IsOptional()
  @IsString()
  time: string;

  @IsOptional()
  @IsInt()
  err: number;

  sha1: string;
}
